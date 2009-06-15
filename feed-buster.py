import cgi
import os
import re
import urllib
import urlparse
import mimetypes
import xpath

import math
from xml.dom import minidom
from xml.sax import saxutils 
from django.utils import simplejson 
from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.api.urlfetch import DownloadError 
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

class FeedBusterUtils():
  StripHtmlContentTagsRE = re.compile(r'(?i)((<head[^>]*?>.*?</head>)|(<style[^>]*?>.*?</style>)|(<script[^>]*?>.*?</script>)|(<object[^>]*?>.*?</object>)|(<embed[^>]*?>.*?</embed>)|(<applet[^>]*?>.*?</applet>)|(<noframes[^>]*?>.*?</noframes>)|(<noscript[^>]*?>.*?</noscript>)|(<noembed[^>]*?>.*?</noembed>))')
  InsertNewlineAfterTagsRE = re.compile(r'(?i)(</((address)|(blockquote)|(center)|(del)|(div)|(h[1-9])|(ins)|(isindex)|(p)|(pre)|(dir)|(dl)|(dt)|(dd)|(li)|(menu)|(ol)|(ul)|(table)|(th)|(td)|(caption)|(form)|(button)|(fieldset)|(legend)|(input)|(label)|(select)|(optgroup)|(option)|(textarea)|(frameset)|(frame)|(iframe))>)')
  StripAllHtmlTagsRE = re.compile(r'<.*?>')
  
  @staticmethod
  def getRequestParams(requestQueryString, paramsList):
    requestQueryString = "&" + requestQueryString
    paramIndexes = [(param, requestQueryString.find('&' + param + '=')) for param in paramsList]
    paramIndexes = sorted(filter(lambda x: x[1]!=-1, paramIndexes),key=lambda x:x[1])
    paramIndexes = [(paramIndexes[i][0], paramIndexes[i][1] + len(paramIndexes[i][0]) + 2, len(requestQueryString) if (i == (len(paramIndexes)-1)) else paramIndexes[i+1][1])
                    for i in range(len(paramIndexes))]
    return dict((param[0], urllib.unquote(requestQueryString[param[1]:param[2]])) for param in paramIndexes)

  @staticmethod
  def fetchContent(contentUrl, maxRetryCount=2, maxTimeout=10):
    contentUrl = contentUrl.replace(" ", "%20")
    for i in range(maxRetryCount):
      try: 
        fetchResult = urlfetch.fetch(contentUrl, deadline=maxTimeout)
        break
      except DownloadError: 
        fetchResult = None
    if not(fetchResult) or fetchResult.status_code != 200:
      return None
    else:
      return fetchResult.content
      
  @staticmethod
  def fetchContentDOM(contentUrl):
    contentString = FeedBusterUtils.fetchContent(contentUrl)
    return minidom.parseString(contentString)
    
  @staticmethod
  def fetchContentJSON(contentUrl):
    contentString = FeedBusterUtils.fetchContent(contentUrl)
    return simplejson.loads(contentString)
    
  @staticmethod
  def getFeedType(feedTree):
    rootElem = feedTree.documentElement
    rootTagName = rootElem.localName
    if rootTagName.lower() == "rss" or rootTagName.lower() == "rdf":
      return "rss"
    elif rootTagName.lower() == "feed":
      return "atom"
    else:
      return None
  
  @staticmethod
  def stripHtmlTags(htmlString):
    htmlString = FeedBusterUtils.StripHtmlContentTagsRE.sub(' ', htmlString) 
    htmlString = FeedBusterUtils.InsertNewlineAfterTagsRE.sub(r'\1\n', htmlString)
    htmlString = FeedBusterUtils.StripAllHtmlTagsRE.sub('', htmlString)
    return htmlString
    
class CacheControl(webapp.RequestHandler):
  def get(self):
    requestParams = FeedBusterUtils.getRequestParams(self.request.query_string, ["cacheId"])
    if requestParams.has_key("cacheId"):
      result = str(memcache.delete(requestParams["cacheId"]))
      result += "\n"
      result += str(memcache.get_stats())
      return result
    else:
      result = str(memcache.flush_all())
      result += "\n"
      result += str(memcache.get_stats())
      return result
class MediaInjection(webapp.RequestHandler): 
  paramsList = ['inputFeedUrl', 'version', 'webScrape', 'getDescription']
  
  ImageTagSearchRE = re.compile(r'(<img[^>]*?\ssrc=[\'"]{0,1}[^\'"]+["\'\s]{0,1}[^>]*?>)', re.IGNORECASE)
  ImageSrcRE = re.compile(r'.*?src=[\'"]{0,1}([^\s\'"]+)["\'\s]{0,1}.*?', re.IGNORECASE)
  ImageWidthRE = re.compile(r'(.*?width=[\'"]{0,1}(\d+%?)["\'\s]{0,1}.*?)|(.*?style=[\'"]{0,1}[^\'"]*?width\s?:\s?(\d+)px[^\'"]*?["\'\s]{0,1}.*)', re.IGNORECASE)
  ImageHeightRE = re.compile(r'(.*?height=[\'"]{0,1}(\d+%?)["\'\s]{0,1}.*?)|(.*?style=[\'"]{0,1}[^\'"]*?height\s?:\s?(\d+)px[^\'"]*?["\'\s]{0,1}.*)', re.IGNORECASE)
  
  FlickrTagSearchRE = re.compile(r'(<embed[^>]*? src=[\'"]{0,1}[^\'"]+?flickr.com/apps/video/stewart.swf[^\'"]+?["\'\s]{0,1}[^>]*?>)', re.IGNORECASE)
  FlickrPhotoIDRE = re.compile(r'.*?photo_id=(\d+)[\'"&].*?', re.IGNORECASE)
  YoutubeTagSearchRE = re.compile(r'(<embed[^>]*? src=[\'"]{0,1}[^\'"]+?youtube\.com/v/[^\'"]+?["\'\s]{0,1}[^>]*?>)', re.IGNORECASE)
  YoutubePhotoIDRE = re.compile(r'.*?src=[\'"]{0,1}[^\'"]+?youtube.com/v/([^\'"#&?\s;]+)[^\'"]+?["\'\s]{0,1}.*?', re.IGNORECASE)
  VimeoTagSearchRE = re.compile(r'(<embed[^>]*? src=[\'"]{0,1}[^\'"]+?vimeo.com/moogaloop.swf[^\'"]+?["\'\s]{0,1}[^>]*?>)', re.IGNORECASE)
  VimeoPhotoIDRE = re.compile(r'.*?src=[\'"]{0,1}[^\'"]+?vimeo\.com/moogaloop\.swf\?clip_id=([^\'"#&?\s;]+)[^\'"]+?["\'\s]{0,1}.*?', re.IGNORECASE)
  AudioTagSearchRE = re.compile(r'(<a[^>]*? href=[\'"]{0,1}[^\'"]+\.mp3["\'\s]{0,1}[^>]*?>)', re.IGNORECASE)
  AudioSrcRE = re.compile(r'.*?href=[\'"]{0,1}([^\'"]+\.mp3)["\'\s]{0,1}.*?', re.IGNORECASE)
  
  VimeoAPICallUrl = 'http://vimeo.com/api/clip/%s.json'
  FlickrApiCallUrl = 'http://api.flickr.com/services/rest/?method=flickr.photos.getSizes&api_key=5445c27bf055b4beda962ea058416078&photo_id=%s&format=json&nojsoncallback=1'
  Img2JSONApiCallUrl = 'http://img2json.appspot.com/go/?url=%s'
  def getVimeoThumbnail(self, vimeoVideoId):
    vimeoApiCallUrl = MediaInjection.VimeoAPICallUrl % vimeoVideoId
    vimeoApiResponseJson = FeedBusterUtils.fetchContentJSON(vimeoApiCallUrl)
    return vimeoApiResponseJson[0]['thumbnail_large'].replace('\\','')
  
  def getFlickrThumbnail(self, videoId):
    flickrCallUrl = MediaInjection.FlickrApiCallUrl % videoId
    flickrApiResponseJson = FeedBusterUtils.fetchContentJSON(flickrCallUrl)
    for size in flickrApiResponseJson['sizes']['size']:
      if size['label'] == 'Small':
        return size['source'].replace('\\','')
    return None
  
  def getFlickrVideo(self, videoId):
    flickrCallUrl = MediaInjection.FlickrApiCallUrl % videoId
    flickrApiResponseJson = FeedBusterUtils.fetchContentJSON(flickrCallUrl)
    for size in flickrApiResponseJson['sizes']['size']:
      if size['label'] == 'Site MP4':
        return size['source']
    return None
    
  
  def maxResizeImage(self, imageWidth, imageHeight, maxImageWidth = 525.0, maxImageHeight = 175.0):
    if imageWidth == "" or imageHeight == "":
      return imageWidth, imageHeight
    imageWidth = float(imageWidth)
    imageHeight = float(imageHeight)
    if imageWidth < maxImageWidth and imageHeight < maxImageHeight:
      return str(int(imageWidth)), str(int(imageHeight))
    else:
      widthReduction = imageWidth/maxImageWidth
      heightReduction = imageHeight/maxImageHeight
      reduction = widthReduction if widthReduction > heightReduction else heightReduction
      return str(int(math.floor(imageWidth/reduction))), str(int(math.floor(imageHeight/reduction)))
      
  def getImageProperties(self, imageUrl):
    serviceCallUrl = MediaInjection.Img2JSONApiCallUrl % imageUrl
    serviceResultJson = FeedBusterUtils.fetchContent(serviceCallUrl) 
    imageInfo = simplejson.loads(serviceResultJson.replace("\\x00","").replace("'",'"').replace(";","")) if serviceResultJson else None
    if imageInfo is None or imageInfo.has_key('error'):
      imageInfo = None
    else:
      imageInfo = { 'width' : str(imageInfo['width']), 'height' : str(imageInfo['height']), 'mimeType' : imageInfo['mimeType'] }
    return imageInfo
    
  def searchForMediaString(self, stringToParse):
    images = []
    audios = []
    videos = []
                
    #audio
    audioTags = MediaInjection.AudioTagSearchRE.findall(stringToParse)
    for audioTag in audioTags:
      audioSrc = MediaInjection.AudioSrcRE.search(audioTag).group(1)
      audios += [{'mediaType' : 'aud',
                  'url' : audioSrc,
                  'type' : 'audio/mpeg'}]
    
    #video - vimeo 
    videoTags = MediaInjection.VimeoTagSearchRE.findall(stringToParse)
    for videoTag in videoTags:
      videoId = MediaInjection.VimeoPhotoIDRE.search(videoTag).group(1)
      videos += [{'mediaType' : 'vid',
                  'url' : 'http://vimeo.com/moogaloop.swf?clip_id=' + videoId,
                  'thumb' : self.getVimeoThumbnail(videoId),
                  'thumbWidth' : '160',
                  'thumbHeight' : '120',
                  'type' : 'application/x-shockwave-flash'}]
    
    #video - youtube
    videoTags = MediaInjection.YoutubeTagSearchRE.findall(stringToParse)
    for videoTag in videoTags:
      videoId = MediaInjection.YoutubePhotoIDRE.search(videoTag).group(1)
      videos += [{'mediaType' : 'vid',
                  'url' : 'http://www.youtube.com/v/' + videoId,
                  'thumb' : 'http://img.youtube.com/vi/' + videoId + '/2.jpg',
                  'thumbWidth' : '160',
                  'thumbHeight' : '120',
                  'type' : 'application/x-shockwave-flash'}]
                
    #video - flickr
    videoTags = MediaInjection.FlickrTagSearchRE.findall(stringToParse)
    for videoTag in videoTags:
      videoId = MediaInjection.FlickrPhotoIDRE.search(videoTag).group(1)
      videos += [{'mediaType' : 'vid',
          'url' : self.getFlickrVideo(videoId),
          'thumb' : self.getFlickrThumbnail(videoId),
          'thumbWidth' : '160',
          'thumbHeight' : '120',
          'type' : 'application/x-shockwave-flash'}]
                
    # images
    imageTags = MediaInjection.ImageTagSearchRE.findall(stringToParse)
    for imageTag in imageTags:
      imageSrc = MediaInjection.ImageSrcRE.search(imageTag).group(1)
      imageSrc = imageSrc if imageSrc.find("?") == -1 else imageSrc[0:imageSrc.find("?")]
      imageType = mimetypes.guess_type(imageSrc)[0]
      imageWidth = MediaInjection.ImageWidthRE.search(imageTag)
      imageHeight = MediaInjection.ImageHeightRE.search(imageTag)
      if not(imageWidth) or not(imageHeight) or not(imageType):
        imageProperties = self.getImageProperties(imageSrc)
        if not(imageProperties):
          imageHeight = (imageHeight.group(2) if imageHeight.group(2) else imageHeight.group(4)) if imageHeight else ""
          imageWidth = (imageWidth.group(2) if imageWidth.group(2) else imageWidth.group(4)) if imageWidth else ""
          imageType = imageType if imageType else ""
        else:
          imageWidth = imageProperties['width']
          imageHeight = imageProperties['height']
          imageType = imageProperties['mimeType'] if not(imageType) else imageType
      else:
        imageWidth = (imageWidth.group(2) if imageWidth.group(2) else imageWidth.group(4))
        imageHeight = (imageHeight.group(2) if imageHeight.group(2) else imageHeight.group(4))
      
      imageWidth, imageHeight = self.maxResizeImage(imageWidth, imageHeight)
      
      images += [{'mediaType' : 'img', 'url' : imageSrc, 'width' : imageWidth, 'height' : imageHeight, 'type' : imageType}]
    return images+videos+audios
  
  '''def searchForMedia(self, soupString):
    soupString = saxutils.unescape(soupString, {'&quot;' : '"'})
    #soupString = str(soupString)
    mediaSoup = BeautifulSoup.BeautifulSoup(soupString)#, fromEncoding='utf-8')

    images = []
    audios = []
    videos = []
    
    # images
    for image in mediaSoup("img", recursive=True):
      imageSrc = image['src'] if image.has_key('src') else None
      imageType = mimetypes.guess_type(str(imageSrc))[0]
      imageWidth = image['width'] if image.has_key('width') else None
      imageHeight = image['height'] if image.has_key('height') else None

      if not(imageWidth) or not(imageHeight) or not(imageType):
        imageProperties = self.getImageProperties(imageSrc)
        if not(imageProperties):
          continue
        imageWidth = imageProperties['width']
        imageHeight = imageProperties['height']
        imageType = imageProperties['mimeType']
      imageWidth, imageHeight = self.maxResizeImage(imageWidth, imageHeight)
      images += [{'mediaType' : 'img', 'url' : imageSrc, 'width' : imageWidth, 'height' : imageHeight, 'type' : imageType}]

    # video
    for video in mediaSoup.findAll("embed", type="application/x-shockwave-flash", recursive=True):
      if video['src'].find("vimeo.com/moogaloop.swf") > -1:
        videoId = re.search(r'.*?vimeo\.com/moogaloop\.swf\?clip_id=([^\'"#&?\s;]+).*?', video['src'], re.IGNORECASE).group(1)
        videos += [{'mediaType' : 'vid',
                  'url' : 'http://vimeo.com/moogaloop.swf?clip_id=' + videoId,
                  'thumb' : self.getVimeoThumbnail(videoId),
                  'thumbWidth' : '160',
                  'thumbHeight' : '120',
                  'type' : 'application/x-shockwave-flash'}]
      elif video['src'].find("youtube.com/v/") > -1:
        videoId = re.search(r'.*?youtube\.com/v/([^\'"#&?\s;]+).*?', video['src'], re.IGNORECASE).group(1)
        videos += [{'mediaType' : 'vid',
                    'url' : 'http://www.youtube.com/v/' + videoId,
                    'thumb' : 'http://img.youtube.com/vi/' + videoId + '/2.jpg',
                    'thumbWidth' : '160',
                    'thumbHeight' : '120',
                    'type' : 'application/x-shockwave-flash'}]
      elif video['src'].find("flickr.com/apps/video/stewart.swf") > -1:
        videoId = re.search(r'.*?photo_id=(\d+)[\'"&].*?', video['flashvars'], re.IGNORECASE).group(1)
        videos += [{'mediaType' : 'vid',
            'url' : self.getFlickrVideo(videoId),
            'thumb' : self.getFlickrThumbnail(videoId),
            'thumbWidth' : '160',
            'thumbHeight' : '120',
            'type' : 'application/x-shockwave-flash'}]
    
    # audio
    for audio in mediaSoup.findAll("a", href = lambda url: url and url.endswith(".mp3")):
      audios += [{'mediaType' : 'aud',
                  'url' : audio['href'],
                  'type' : 'audio/mpeg'}]

    return images+videos+audios'''
  
  def searchForMediaDOM(self, nodesToCrawl):
    crawledMedia = []
    for nodeToCrawl in nodesToCrawl:
      stringToParse = saxutils.unescape(nodeToCrawl.toxml(), {'&quot;' : '"'})
      crawledMedia += self.searchForMediaString(stringToParse)
    return crawledMedia
    
  def fixRelativeUrls(self, linkNodeUrl, scrapedMediaLinks):
    for mediaLink in scrapedMediaLinks:
      mediaLink['url'] = urlparse.urljoin(linkNodeUrl, mediaLink['url'])
    return scrapedMediaLinks
  
  def addDescription(self, feedTree, descriptionText, oldDescriptions, mediaParent):
    if descriptionText:
      for oldDescription in oldDescriptions:
        mediaParent.removeChild(oldDescription)
      descriptionElem = feedTree.createElement('description')
      descrText = feedTree.createTextNode(descriptionText)
      descriptionElem.appendChild(descrText)
      mediaParent.appendChild(descriptionElem)
    return
    
  def addMediaNode(self, feedTree, mediaLink, mediaParent):
    mediaType = mediaLink['mediaType']
    if mediaType == 'img':
      groupElem = feedTree.createElement('media:group')
      groupElem.setAttribute('xmlns:media','http://search.yahoo.com/mrss/')
      
      contentElem = feedTree.createElement('media:content')
      contentElem.setAttribute('url', mediaLink['url'])
      contentElem.setAttribute('type', mediaLink['type'])
      contentElem.setAttribute('width', mediaLink['width'])
      contentElem.setAttribute('height', mediaLink['height'])
      
      thumbElem = feedTree.createElement('media:thumbnail')
      thumbElem.setAttribute('url', mediaLink['url'])
      thumbElem.setAttribute('width', mediaLink['width'])
      thumbElem.setAttribute('height', mediaLink['height'])
      
      groupElem.appendChild(contentElem)
      groupElem.appendChild(thumbElem)
      mediaParent.appendChild(groupElem)
    elif mediaType == 'vid':
      groupElem = feedTree.createElement('media:group')
      groupElem.setAttribute('xmlns:media','http://search.yahoo.com/mrss/')
      
      contentElem = feedTree.createElement('media:content')
      contentElem.setAttribute('url', mediaLink['url'])
      contentElem.setAttribute('type', mediaLink['type'])
      contentElem.setAttribute('width', "")
      contentElem.setAttribute('height', "")

      thumbElem = feedTree.createElement('media:thumbnail')
      thumbElem.setAttribute('url', mediaLink['thumb'])
      thumbElem.setAttribute('width', mediaLink['thumbWidth'])
      thumbElem.setAttribute('height', mediaLink['thumbHeight'])
      
      groupElem.appendChild(thumbElem)  
      groupElem.appendChild(contentElem)
      mediaParent.appendChild(groupElem)
    elif mediaType == 'aud':
      groupElem = feedTree.createElement('media:group')
      groupElem.setAttribute('xmlns:media','http://search.yahoo.com/mrss/')
      
      contentElem = feedTree.createElement('media:content')
      contentElem.setAttribute('url', mediaLink['url'])
      contentElem.setAttribute('type', mediaLink['type'])
      
      groupElem.appendChild(contentElem)
      mediaParent.appendChild(groupElem)
    return         
  
  '''def createMediaNode(self, feedSoup, mediaLink):
    mediaType = mediaLink['mediaType']

    if mediaType == 'img':
      groupTag = BeautifulSoup.Tag(feedSoup, "media:group", [("xmlns:media", "http://search.yahoo.com/mrss/")])
      contentTag = BeautifulSoup.Tag(feedSoup, "media:content", [("url", str(mediaLink["url"])), ("type", mediaLink["type"]), ("width", mediaLink["width"]), ("height", mediaLink["height"])])
      thumbTag = BeautifulSoup.Tag(feedSoup, "media:thumbnail", [("url", mediaLink["url"]), ("width", mediaLink["width"]), ("height", mediaLink["height"])])
      groupTag.append(contentTag)
      groupTag.append(thumbTag)
      return groupTag
      
    elif mediaType == 'vid':
      groupTag = BeautifulSoup.Tag(feedSoup, "media:group", [("xmlns:media", "http://search.yahoo.com/mrss/")])
      contentTag = BeautifulSoup.Tag(feedSoup, "media:content", [("url", mediaLink["url"]), ("type", mediaLink["type"]), ("width", ""), ("height", "")])
      thumbTag = BeautifulSoup.Tag(feedSoup, "media:thumbnail", [("url", mediaLink["thumb"]), ("width", mediaLink["thumbWidth"]), ("height", mediaLink["thumbHeight"])])
      groupTag.append(contentTag)
      groupTag.append(thumbTag)
      return groupTag

    elif mediaType == 'aud':
      groupTag = BeautifulSoup.Tag(feedSoup, "media:group", [("xmlns:media", "http://search.yahoo.com/mrss/")])
      contentTag = BeautifulSoup.Tag(feedSoup, "media:content", [("url", mediaLink["url"]), ("type", mediaLink["type"])])
      groupTag.append(contentTag)
      return groupTag
    else:
      return None'''
  
  def isNotAdvertising(self, url):
    return True

  def isSmallImage(self, mediaItem):
    if mediaItem['mediaType']=='img':
      if mediaItem.has_key('width') and mediaItem.has_key('height') and mediaItem['width'] != "" and mediaItem['height'] != "":
        if int(mediaItem['width'].replace("%", "")) <= 20 or int(mediaItem['height'].replace("%", "")) <= 20:
          return False
        else:
          return True
      else:
        return True
    return True 
  
  def filterFeedUrl(self, feedUrl):
    if feedUrl.startswith("http://feeds.postrank.com/channel/") and feedUrl.endswith('/'):
      return feedUrl[0:-1]
    else:
      return feedUrl
  
  def get(self):
    #memcache.flush_all()
    requestParams = FeedBusterUtils.getRequestParams(self.request.query_string, MediaInjection.paramsList) 
    feedUrl = self.filterFeedUrl(requestParams['inputFeedUrl'])
    webScrape = requestParams['webScrape'] if requestParams.has_key('webScrape') else None
    getDescription = int(requestParams['getDescription']) if requestParams.has_key('getDescription') else None
    feedTree = FeedBusterUtils.fetchContentDOM(feedUrl)
    feedType = FeedBusterUtils.getFeedType(feedTree)
    
    #todo - replace regex feed parsing with feedparser
    if feedType == 'rss':
      parsingParams = { 'items' : '(child::*[local-name() = "channel"]/child::*[local-name() = "item"]) | (child::*[local-name() = "item"])',# 'items' : '//*[local-name() = "channel"]/*[local-name() = "item"]', 
                        'link' : 'child::*[local-name() = "link" or local-name() = "origLink"]/node()',
                        'id' : 'child::*[local-name() = "guid"]/node()',
                        'updated' : 'child::*[local-name() = "pubDate" or local-name() = "date" local-name() = "modified"]',
                        'published' : 'issued',
                        'description' : 'child::*[local-name() = "description"]',
                        'content' : 'child::*[local-name() = "encoded"]',
                        'existingMedia' : 'child::*[(namespace-uri() = "http://search.yahoo.com/mrss/")and (local-name() = "thumbnail" or local-name() = "content" or local-name() = "group")]' }
    elif feedType == 'atom':
      parsingParams = { 'items' : 'child::*[local-name() = "entry"]', 
                        'link' : 'child::*[local-name() = "link" and (@rel="alternate" or not(@rel))]/@href',
                        'id' : 'child::*[local-name() = "id"]/node()',
                        'updated' : 'child::*[local-name() = "updated"]',
                        'published' : 'published',
                        'description' : 'child::*[local-name() = "summary"]',
                        'content' : 'child::*[local-name() = "content"]',
                        'existingMedia' : 'child::*[(namespace-uri() = "http://search.yahoo.com/mrss/")and (local-name() = "thumbnail" or local-name() = "content" or local-name() = "group")]' }
    else:
      return
    
    # crawl feed or web post
    feedItems = xpath.find(parsingParams['items'], feedTree.documentElement)
    crawledMedia = []
    processedItems = 0
    
    for feedItemIndex in range(len(feedItems)):
      if processedItems >= 20:
        break
      feedItem = feedItems[feedItemIndex]
      itemId = xpath.find(parsingParams['id'], feedItem)
      if not(itemId):
        itemId = xpath.find(parsingParams['link'], feedItem)[0].nodeValue
      else:
        itemId = itemId[0].nodeValue
      itemHash = hash(feedItem.toxml())
      cacheId = itemId + (('_' + webScrape) if webScrape else "")
      
      cachedMedia = memcache.get(cacheId)
      newDescription = None
      if cachedMedia and cachedMedia['itemHash'] == itemHash:
        scrapedMediaLinks = cachedMedia['crawledMedia']
        processedItems += 1
        if cachedMedia.has_key("newDescription"):
          newDescription = cachedMedia['newDescription']
      else:
        if webScrape:
          processedItems += 8
          linkNodeUrl = xpath.find(parsingParams['link'], feedItem)[0].nodeValue
          linkResultString = FeedBusterUtils.fetchContent(linkNodeUrl)
          scrapedMediaLinks = self.searchForMediaString(linkResultString)
          scrapedMediaLinks = self.fixRelativeUrls(linkNodeUrl, scrapedMediaLinks)
        else:
          processedItems += 1
          contentCrawlNodes = xpath.find(parsingParams['content'], feedItem)
          scrapedMediaLinks = self.searchForMediaDOM(contentCrawlNodes)
          if len(scrapedMediaLinks) == 0:
            descriptionCrawlNodes = xpath.find(parsingParams['description'], feedItem)
            scrapedMediaLinks = self.searchForMediaDOM(descriptionCrawlNodes)
        
        if getDescription:
          newDescription = xpath.find(parsingParams['content'], feedItem)
          if newDescription:
            newDescription = newDescription[0].firstChild.data
            newDescription = saxutils.unescape(newDescription, {'&quot;' : '"'})
            newDescription = FeedBusterUtils.stripHtmlTags(newDescription)
            if len(newDescription) > getDescription:
              newDescription = newDescription[0:getDescription-3] + "..."
            else:
              newDescription = newDescription[0:getDescription]
            
      existingMedia = xpath.find(parsingParams['existingMedia'], feedItem)
      for existingMediaItem in existingMedia:
        if existingMediaItem.localName == "content":
          if existingMediaItem.hasAttribute("type") and existingMediaItem.getAttribute("type").startswith("image"):
            imageSrc = existingMediaItem.getAttribute("url")
            imageWidth = existingMediaItem.getAttribute("width")
            imageHeight = existingMediaItem.getAttribute("height")
            imageType = existingMediaItem.getAttribute("type")
            scrapedMediaLinks += [{'mediaType' : 'img', 'url' : imageSrc, 'width' : imageWidth, 'height' : imageHeight, 'type' : imageType}]
        feedItem.removeChild(existingMediaItem)
      
      crawledMedia += [{'feedNode' : feedItem, 'itemHash' : itemHash, 'mediaLinks' : scrapedMediaLinks, 'cacheId' : cacheId, 'newDescription' : newDescription}]
      #self.response.out.write(str(scrapedMediaLinks))
    
    # return
    # count repeated links
    mediaCount = {}
    for itemMedia in crawledMedia:
      for mediaLink in itemMedia['mediaLinks']:
        mediaCount[mediaLink['url']] = mediaCount[mediaLink['url']]+1 if mediaCount.has_key(mediaLink['url']) else 0
    
    # filters 
    for itemMedia in crawledMedia:
      # nonidentified media
      itemMedia['mediaLinks'] = filter(lambda x: x['type']!=None and x['type']!="", itemMedia['mediaLinks'])
      # small images
      itemMedia['mediaLinks'] = filter(self.isSmallImage, itemMedia['mediaLinks'])
      # ads
      itemMedia['mediaLinks'] = filter(self.isNotAdvertising, itemMedia['mediaLinks'])
      # write to cache
      memcache.set(itemMedia['cacheId'], {'itemHash' : itemMedia['itemHash'], 'crawledMedia' : itemMedia['mediaLinks']})
      
    # filters 
    for itemMedia in crawledMedia:
      # repeated media
      itemMedia['mediaLinks'] = filter(lambda x: mediaCount[x['url']]<3, itemMedia['mediaLinks'])
    
    #generate media enclosure XML elements
    for itemMedia in crawledMedia:
      feedNode = itemMedia['feedNode']
      newDescription = itemMedia['newDescription']
      descriptionNode = xpath.find(parsingParams['description'], feedNode)
      self.addDescription(feedTree, newDescription, descriptionNode, feedNode)
      for mediaLink in itemMedia['mediaLinks']:
        self.addMediaNode(feedTree, mediaLink, feedNode)
          
    # write output feed
    self.response.headers['Content-Type'] = 'application/%s+xml' % feedType
    self.response.out.write(feedTree.toxml())
    return
  
  '''def get_new(self):
    import BeautifulSoup
    #memcache.flush_all()
    requestParams = FeedBusterUtils.getRequestParams(self.request.query_string, MediaInjection.paramsList) 
    feedUrl = self.filterFeedUrl(requestParams['inputFeedUrl'])
    webScrape = requestParams['webScrape'] if requestParams.has_key('webScrape') else None
    getDescription = int(requestParams['getDescription']) if requestParams.has_key('getDescription') else None

    feedUrl = self.filterFeedUrl(feedUrl)
    if not(feedUrl): return
    
    feedString = FeedBusterUtils.fetchContent(feedUrl) 
    originSoup = BeautifulSoup.BeautifulStoneSoup(feedString, fromEncoding="utf-8", selfClosingTags=['media:content', 'media:thumbnail'])
    feedSoup = originSoup.find({'rss':True, 'feed':True}, recursive=False)
    if feedSoup is None: return
    feedType = feedSoup.name
    
    if feedType == 'rss':
      soupParser = { 'items' : lambda feedSoup: feedSoup.channel.findAll(['item'], recursive=False), 
                     'link' : lambda itemSoup: itemSoup.find(["link", "origLink"], recursive=False),
                     'id' : lambda itemSoup: itemSoup.find(["guid"], recursive=False),
                     'updated' : lambda itemSoup: itemSoup.find(["pubDate", "date", "modified"], recursive=False),
                     'published' : 'issued',
                     'description' : lambda itemSoup: itemSoup.find(["description"], recursive=False),
                     'content' : lambda itemSoup: itemSoup.find(["content:encoded"], recursive=False),
                     'existingMedia' : lambda itemSoup: itemSoup.findAll(["media:thumbnail", "media:content", "media:group"], recursive=True)}
    elif feedType == 'feed':
      feedType = 'atom'
      def getLink(itemSoup): 
        retVal = itemSoup.find(["link"], rel="alternate", recursive=False)
        if not(retVal):
          retVal = itemSoup.find(["link"], rel=None, recursive=False)
        return retVal['href']
      soupParser = { 'items' : lambda feedSoup: feedSoup.findAll(['entry'], recursive=False), 
                     'link' : getLink, 
                     'id' : lambda itemSoup: itemSoup.find(["id"], recursive=False),
                     'updated' : lambda itemSoup: itemSoup.find(["updated"], recursive=False),
                     'published' : 'published',
                     'description' : lambda itemSoup: itemSoup.find(["summary"], recursive=False),
                     'content' : lambda itemSoup: itemSoup.find(["content"], recursive=False),
                     'existingMedia' : lambda itemSoup: itemSoup.findAll(["media:thumbnail", "media:content", "media:group"], recursive=True)}
    else:
      return
    
    # crawl feed or web post
    feedItems = soupParser['items'](feedSoup)
    crawledMedia = []
    processedItems = 0
    
    for feedItemIndex in range(len(feedItems)):
      if processedItems >= 12:
        break
      feedItem = feedItems[feedItemIndex]
      itemId = soupParser['id'](feedItem) 
      if not(itemId):
        itemId = soupParser['link'](feedItem).string
      else:
        itemId = itemId.string
      
      itemHash = hash(str(feedItem))
      cacheId = itemId + (('_' + webScrape) if webScrape else "")
      
      existingMedia = soupParser['existingMedia'](feedItem)
      for existingMediaItem in existingMedia:
        existingMediaItem.extract()
      
      description = None
      cachedMedia = memcache.get(cacheId)
      if cachedMedia and cachedMedia['itemHash'] == itemHash:
        scrapedMediaLinks = cachedMedia['crawledMedia']
      else:        
        #self.response.out.write("crawl0\n")
        if webScrape:
          linkNodeUrl = soupParser['link'](feedItem).string
          linkResultString = FeedBusterUtils.fetchContent(linkNodeUrl)
          scrapedMediaLinks = self.searchForMedia(linkResultString)
          processedItems += 3
          #self.response.out.write("crawl1\n")
        else:
          #self.response.out.write("crawl2\n")
          contentNode = soupParser['content'](feedItem)
          processedItems += 1
          if contentNode:
            try:
              content = "".join([j for j in contentNode])
              scrapedMediaLinks = self.searchForMedia(content)
            except:
              try:
                content = "".join([j for j in contentNode])
                content = saxutils.unescape(content, {'&quot;' : '"'})
                scrapedMediaLinks = self.searchForMediaString(content)
              except:
                continue  
          if not(contentNode) or len(scrapedMediaLinks) == 0:
            #continue
            processedItems += 1
            descriptionCrawlNode = soupParser['description'](feedItem)
            if descriptionCrawlNode:
              #self.response.out.write(saxutils.unescape(descriptionSoup, {'&quot;' : '"'}) + "crawl4\n")
              try:
                descriptionSoup = "".join([j for j in descriptionCrawlNode])
                scrapedMediaLinks = self.searchForMedia(descriptionSoup)
              except:
                try:
                  descriptionSoup = "".join([j for j in descriptionCrawlNode])
                  descriptionSoup = saxutils.unescape(descriptionSoup, {'&quot;' : '"'})
                  scrapedMediaLinks = self.searchForMediaString(descriptionSoup)
                except:
                  continue  
              #self.response.out.write("error!!!!\n\n\n"+ saxutils.unescape(descriptionSoup, {'&quot;' : '"'})+"\n\n\n\n")
              #continue
              #descriptionSoup = saxutils.unescape(descriptionSoup, {'&quot;' : '"'})
              #descriptionSoup = descriptionSoup.decode()
              #sp1 = BeautifulSoup.BeautifulSoup(descriptionSoup, fromEncoding="utf-8")
              #self.response.out.write(descriptionSoup)
              #self.response.out.write(str(scrapedMediaLinks) + "conter\n")
              #continue
            if not(descriptionCrawlNode) or len(scrapedMediaLinks) == 0:
              #self.response.out.write("crawl5\n")
              continue
        
        # description parsing
        #self.response.out.write("description0\n")
        if getDescription:
          contentSoup = soupParser['content'](feedItem)
          #self.response.out.write("description1\n")
          if contentSoup:
            #self.response.out.write("description2\n")
            descriptionText = ''.join(contentSoup.findAll(text=True))[0:getDescription]
            description = soupParser['description'](feedItem)
            if description:
              for descriptionItem in description:
                description.extract()
            
            descriptionSoup = BeautifulSoup.NavigableString(descriptionText)
            description.append(descriptionSoup)

      
      crawledMedia += [{'feedNode' : feedItem, 'itemHash' : itemHash, 'mediaLinks' : scrapedMediaLinks, 'cacheId' : cacheId, 'description' : description}]
    
    # count repeated links
    mediaCount = {}
    for itemMedia in crawledMedia:
      for mediaLink in itemMedia['mediaLinks']:
        mediaCount[mediaLink['url']] = mediaCount[mediaLink['url']]+1 if mediaCount.has_key(mediaLink['url']) else 0
    
    # filters 
    for itemMedia in crawledMedia:
      # nonidentified media
      itemMedia['mediaLinks'] = filter(lambda x: x['type']!=None, itemMedia['mediaLinks'])
      # small images
      itemMedia['mediaLinks'] = filter(self.isSmallImage, itemMedia['mediaLinks'])
      # ads
      itemMedia['mediaLinks'] = filter(self.isNotAdvertising, itemMedia['mediaLinks'])
      # write to cache
      memcache.set(itemMedia['cacheId'], {'itemHash' : itemMedia['itemHash'], 'crawledMedia' : itemMedia['mediaLinks']})
      
    # filters 
    for itemMedia in crawledMedia:
      # repeated media
      itemMedia['mediaLinks'] = filter(lambda x: mediaCount[x['url']]<3, itemMedia['mediaLinks'])

    #generate media enclosure XML elements
    for itemMedia in crawledMedia:
      for mediaLink in itemMedia['mediaLinks']:
        mediaElem = self.createMediaNode(originSoup, mediaLink)
        itemMedia['feedNode'].append(mediaElem)
	  
		# write output feed
    self.response.headers['Content-Type'] = 'application/%s+xml' % feedType
    self.response.out.write(str(originSoup))
    return           
    
  def get(self):
    requestParams = FeedBusterUtils.getRequestParams(self.request.query_string, MediaInjection.paramsList) 
    if requestParams.has_key('version'):
      if requestParams['version'] == "old":
        #self.response.out.write("1")
        return self.get_old()
      elif requestParams['version'] == "new":
        #self.response.out.write("2")
        return self.get_new()
    else:
      #self.response.out.write("1")
      return self.get_old()'''
    
application = webapp.WSGIApplication([('/mediaInjection.*', MediaInjection), ('/cache.*', CacheControl)], debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()