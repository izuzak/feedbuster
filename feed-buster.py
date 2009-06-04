import cgi
import os
import re
import urllib
import urlparse
import mimetypes
import xpath
import BeautifulSoup

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
  
class CacheControl(webapp.RequestHandler):
  def get(self):
    return str(memcache.flush_all())
    
class Redirect(webapp.RequestHandler):
  def get(self):
    self.redirect("http://code.google.com/p/feed-buster/")
    
class MediaInjection(webapp.RequestHandler): 
  
  # simple api - http://vimeo.com/api/clip/2539741.json
  # advanced api - vimeo.videos.getThumbnailUrl
  def getVimeoThumbnail(self, vimeoVideoId):
    vimeoApiCallUrl = 'http://vimeo.com/api/clip/%s.json' % vimeoVideoId
    vimeoApiResponseJson = FeedBusterUtils.fetchContentJSON(vimeoApiCallUrl)
    return vimeoApiResponseJson[0]['thumbnail_large'].replace('\\','')
  
  # http://www.flickr.com/services/api/flickr.photos.getSizes.html
  def getFlickrThumbnail(videoId):
    flickrCallUrl = 'http://api.flickr.com/services/rest/?method=flickr.photos.getSizes&api_key=5445c27bf055b4beda962ea058416078&photo_id=%s&format=json&nojsoncallback=1' % videoId
    flickrApiResponseJson = FeedBusterUtils.fetchContentJSON(flickrCallUrl)
    for size in flickrApiResponseJson['sizes']['size']:
      if size['label'] == 'Small':
        return size['source'].replace('\\','')
    return Null
  
  def maxResizeImage(self, imageWidth, imageHeight, maxImageWidth = 525.0, maxImageHeight = 175.0):
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
    serviceCallUrl = 'http://img2json.appspot.com/go/?url='+imageUrl
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
    audioTags = re.findall(r'(<a[^>]*? href=[\'"]{0,1}[^\'"]+\.mp3["\'\s]{0,1}[^>]*?>)', stringToParse, re.IGNORECASE)
    for audioTag in audioTags:
      audioSrc = re.search(r'.*?href=[\'"]{0,1}([^\'"]+\.mp3)["\'\s]{0,1}.*?', audioTag, re.IGNORECASE)
      audios += [{'mediaType' : 'aud',
                  'url' : audioSrc.group(1),
                  'type' : 'audio/mpeg'}]
    #video - vimeo 
    videoTags = re.findall(r'(<embed[^>]*? src=[\'"]{0,1}[^\'"]+?vimeo.com/moogaloop.swf[^\'"]+?["\'\s]{0,1}[^>]*?>)', stringToParse, re.IGNORECASE)
    for videoTag in videoTags:
      videoId = re.search(r'.*?src=[\'"]{0,1}[^\'"]+?vimeo\.com/moogaloop\.swf\?clip_id=([^\'"#&?\s;]+)[^\'"]+?["\'\s]{0,1}.*?', videoTag, re.IGNORECASE)
      videoId = videoId.group(1)
      videos += [{'mediaType' : 'vid',
                  'url' : 'http://vimeo.com/moogaloop.swf?clip_id=' + videoId,
                  'thumb' : self.getVimeoThumbnail(videoId),
                  'thumbWidth' : '160',
                  'thumbHeight' : '120',
                  'type' : 'application/x-shockwave-flash'}]
    #video - youtube
    videoTags = re.findall(r'(<embed[^>]*? src=[\'"]{0,1}[^\'"]+?youtube\.com/v/[^\'"]+?["\'\s]{0,1}[^>]*?>)', stringToParse, re.IGNORECASE)
    for videoTag in videoTags:
      videoId = re.search(r'.*?src=[\'"]{0,1}[^\'"]+?youtube.com/v/([^\'"#&?\s;]+)[^\'"]+?["\'\s]{0,1}.*?', videoTag, re.IGNORECASE)
      videoId = videoId.group(1)
      videos += [{'mediaType' : 'vid',
                  'url' : 'http://www.youtube.com/v/' + videoId,
                  'thumb' : 'http://img.youtube.com/vi/' + videoId + '/2.jpg',
                  'thumbWidth' : '160',
                  'thumbHeight' : '120',
                  'type' : 'application/x-shockwave-flash'}]
                
                # TODO: video - flickr
                #<object type="application/x-shockwave-flash" width="500" height="375" data="http://www.flickr.com/apps/video/stewart.swf?v=71377" classid="clsid:D27CDB6E-AE6D-11cf-96B8-444553540000">
                #       <param name="flashvars" value="intl_lang=en-us&#038;photo_secret=0cd85ca6c8&#038;photo_id=3473039350"></param>
                #       <param name="movie" value="http://www.flickr.com/apps/video/stewart.swf?v=71377"></param>
                #       <param name="bgcolor" value="#000000"></param><param name="allowFullScreen" value="true"></param>
                #       <embed type="application/x-shockwave-flash" src="http://www.flickr.com/apps/video/stewart.swf?v=71377" bgcolor="#000000" allowfullscreen="true" flashvars="intl_lang=en-us&#038;photo_secret=0cd85ca6c8&#038;photo_id=3473039350" height="375" width="500"></embed>
                # </object>
                
    # images
    imageTags = re.findall(r'(<img[^>]*?\ssrc=[\'"]{0,1}[^\'"]+["\'\s]{0,1}[^>]*?>)', stringToParse, re.IGNORECASE)
    for imageTag in imageTags:
      imageSrc = re.search(r'.*?src=[\'"]{0,1}([^\s\'"]+)["\'\s]{0,1}.*?', imageTag, re.IGNORECASE).group(1)
      imageType = mimetypes.guess_type(imageSrc)[0]
      imageWidth = re.search(r'.*?width=[\'"]{0,1}(\d+%?)["\'\s]{0,1}.*?', imageTag, re.IGNORECASE)
      if not(imageWidth):
        imageWidth = re.search(r'.*?style=[\'"]{0,1}[^\'"]*?width\s?:\s?(\d+)px[^\'"]*?["\'\s]{0,1}.*', imageTag, re.IGNORECASE)
      imageHeight = re.search(r'.*?height=[\'"]{0,1}(\d+%?)["\'\s]{0,1}.*?', imageTag, re.IGNORECASE)
      if not(imageHeight):
        imageHeight = re.search(r'.*?style=[\'"]{0,1}[^\'"]*?height\s?:\s?(\d+)px[^\'"]*?["\'\s]{0,1}.*', imageTag, re.IGNORECASE)
        
      if not(imageWidth) or not(imageHeight) or not(imageType):
        imageProperties = self.getImageProperties(imageSrc)
        if not(imageProperties):
          continue
        imageWidth = imageProperties['width']
        imageHeight = imageProperties['height']
        imageType = imageProperties['mimeType']
      else:
        imageWidth = imageWidth.group(1)
        imageHeight = imageHeight.group(1)
        
      imageWidth, imageHeight = self.maxResizeImage(imageWidth, imageHeight)

      images += [{'mediaType' : 'img', 'url' : imageSrc, 'width' : imageWidth, 'height' : imageHeight, 'type' : imageType}]
    return images+videos+audios
  
  def searchForMedia(self, soupString):
    soupString = saxutils.unescape(str(soupString), {'&quot;' : '"'})
    mediaSoup = BeautifulSoup.BeautifulSoup(soupString, fromEncoding='utf-8')
    images = []
    audios = []
    videos = []
    
    # images
    for image in mediaSoup("img", recursive=True):
      imageSrc = image['src'] if image.has_key('src') else None
      imageType = mimetypes.guess_type(str(imageSrc))[0]
      imageWidth = image['width'] if image.has_key('width') else None
      #imageHeight = re.search(r'.*?style=[\'"]{0,1}[^\'"]*?height\s?:\s?(\d+)px[^\'"]*?["\'\s]{0,1}.*', imageTag, re.IGNORECASE)
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
        videoId = re.search(r'.*?flickr\.com/apps/video/stewart\.swf?v=([^\'"#&?\s;]+).*?', video['src'], re.IGNORECASE).group(1)
        videos += [{'mediaType' : 'vid',
            'url' : 'http://www.flickr.com/apps/video/stewart\.swf?v=' + videoId,
            'thumb' : self.getFlickrThumbnail(videoId),
            'thumbWidth' : '160',
            'thumbHeight' : '120',
            'type' : 'application/x-shockwave-flash'}]
    
    # audio
    for audio in mediaSoup.findAll("a", href = lambda url: url.endswith(".mp3")):
      audios += [{'mediaType' : 'aud',
                  'url' : audio['href'],
                  'type' : 'audio/mpeg'}]

    return images+videos+audios
  
  def searchForMediaDOM(self, nodesToCrawl):
    crawledMedia = []
    for nodeToCrawl in nodesToCrawl:
      stringToParse = saxutils.unescape(nodeToCrawl.toxml(), {'&quot;' : '"'})
      crawledMedia += self.searchForMediaString(stringToParse)
    return crawledMedia
  
  def createMediaNode(self, feedTree, mediaLink):
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
      return groupElem
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
      return groupElem
    elif mediaType == 'aud':
      groupElem = feedTree.createElement('media:group')
      groupElem.setAttribute('xmlns:media','http://search.yahoo.com/mrss/')
      
      contentElem = feedTree.createElement('media:content')
      contentElem.setAttribute('url', mediaLink['url'])
      contentElem.setAttribute('type', mediaLink['type'])
      
      groupElem.appendChild(contentElem)
      return groupElem
    else:
      return None
  
  def createMediaNode(self, feedSoup, mediaLink):
    mediaType = mediaLink['mediaType']

    if mediaType == 'img':
      groupTag = BeautifulSoup.Tag(feedSoup, "media:group", [("media", "http://search.yahoo.com/mrss/")])
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
      return None
  
  def isAdvertising(self, url):
    return True

  def isSmallImage(self, mediaItem):
    if mediaItem['mediaType']=='img':
      if mediaItem.has_key('width') and mediaItem.has_key('height'):
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
  
  def get_old(self):
    requestParams = FeedBusterUtils.getRequestParams(self.request.query_string, ['inputFeedUrl', 'webScrape', 'getDescription']) 
    feedUrl = self.processFeedUrl(requestParams['inputFeedUrl'])
    webScrape = requestParams['webScrape'] if requestParams.has_key('webScrape') else None
    getDescription = int(requestParams['getDescription']) if requestParams.has_key('getDescription') else None
    feedTree = FeedBusterUtils.fetchContentDOM(feedUrl)
    feedType = FeedBusterUtils.getFeedType(feedTree)
    
    #todo - replace regex feed parsing with feedparser
    if feedType == 'rss':
      parsingParams = { 'items' : '//*[local-name() = "channel"]/*[local-name() = "item"]', 
                        'link' : '*[local-name() = "link" or local-name() = "origLink"]/node()',
                        'id' : '*[local-name() = "guid"]/node()',
                        'updated' : '*[local-name() = "pubDate" or local-name() = "date" local-name() = "modified"]',
                        'published' : 'issued',
                        'description' : '*[local-name() = "description"]',
                        'content' : '*[local-name() = "encoded"]',
                        'existingMedia' : '*[(namespace-uri() = "http://search.yahoo.com/mrss/")and (local-name() = "thumbnail" or local-name() = "content" or local-name() = "group")]' }
    elif feedType == 'atom':
      parsingParams = { 'items' : '//*[local-name() = "entry"]', 
                        'link' : '*[local-name() = "link" and (@rel="alternate" or not(@rel))]/@href',
                        'id' : '*[local-name() = "id"]/node()',
                        'updated' : '*[local-name() = "updated"]',
                        'published' : 'published',
                        'description' : '*[local-name() = "summary"]',
                        'content' : '*[local-name() = "content"]',
                        'existingMedia' : '*[(namespace-uri() = "http://search.yahoo.com/mrss/")and (local-name() = "thumbnail" or local-name() = "content" or local-name() = "group")]' }
    else:
      return
          
                # crawl feed or web post
    feedItems = xpath.find(parsingParams['items'], feedTree.documentElement)
    crawledMedia = []

    for feedItemIndex in range(len(feedItems)):
      if feedItemIndex >= 4:
        continue
      feedItem = feedItems[feedItemIndex]
      itemId = xpath.find(parsingParams['id'], feedItem)
      if not(itemId):
        itemId = xpath.find(parsingParams['link'], feedItem)[0].nodeValue
      else:
        itemId = itemId[0].nodeValue
      itemHash = hash(feedItem.toxml())
      cacheId = itemId + (('_' + webScrape) if webScrape else "")
      
      cachedMedia = memcache.get(cacheId)
      if cachedMedia and cachedMedia['itemHash'] == itemHash:
        scrapedMediaLinks = cachedMedia['crawledMedia']
      else:
        if webScrape:
          linkNodeUrl = xpath.find(parsingParams['link'], feedItem)[0].nodeValue
          linkResultString = FeedBusterUtils.fetchContent(linkNodeUrl)
          scrapedMediaLinks = self.searchForMediaString(linkResultString)
        else:
          contentCrawlNodes = xpath.find(parsingParams['content'], feedItem)
          scrapedMediaLinks = self.searchForMediaDOM(contentCrawlNodes)
          if len(scrapedMediaLinks) == 0:
            descriptionCrawlNodes = xpath.find(parsingParams['description'], feedItem)
            scrapedMediaLinks = self.searchForMediaDOM(descriptionCrawlNodes)
      
      if getDescription:
        return
        # todo - http://nadeausoftware.com/articles/2007/09/php_tip_how_strip_html_tags_web_page
        # provjeri jel uopce ima contenta
        # newDescription = xpath.find(parsingParams['content'], feedItem)[0].firstChild()
        # newDescription = saxutils.unescape(newDescription.toxml(), {'&quot;' : '"'})
        # self.response.out.write(newDescription)
        # newDescription = re.sub(r'<.*?>', '', newDescription)[0:getDescription]
        # self.response.out.write(newDescription)
      
      crawledMedia += [{'feedNode' : feedItem, 'itemHash' : itemHash, 'mediaLinks' : scrapedMediaLinks, 'cacheId' : cacheId}]
      existingMedia = xpath.find(parsingParams['existingMedia'], feedItem)
      for existingMediaItem in existingMedia:
        feedItem.removeChild(existingMediaItem)

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
      itemMedia['mediaLinks'] = filter(self.isAdvertising, itemMedia['mediaLinks'])
      # write to cache
      memcache.set(itemMedia['cacheId'], {'itemHash' : itemMedia['itemHash'], 'crawledMedia' : itemMedia['mediaLinks']})
      
    # filters 
    for itemMedia in crawledMedia:
      # repeated media
      itemMedia['mediaLinks'] = filter(lambda x: mediaCount[x['url']]<3, itemMedia['mediaLinks'])

    #generate media enclosure XML elements
    for itemMedia in crawledMedia:
      for mediaLink in itemMedia['mediaLinks']:
        mediaElem = self.createMediaNode(feedTree, mediaLink)
        itemMedia['feedNode'].appendChild(mediaElem)
          
                # write output feed
    self.response.headers['Content-Type'] = 'application/%s+xml' % feedType
    self.response.out.write(feedTree.toxml())
    return
  
  def get(self):
    #memcache.flush_all()
    requestParams = FeedBusterUtils.getRequestParams(self.request.query_string, ['inputFeedUrl', 'webScrape', 'getDescription']) 
    feedUrl = self.filterFeedUrl(requestParams['inputFeedUrl'])
    webScrape = requestParams['webScrape'] if requestParams.has_key('webScrape') else None
    getDescription = 100 #int(requestParams['getDescription']) if requestParams.has_key('getDescription') else None

    feedUrl = self.filterFeedUrl(feedUrl)
    if not(feedUrl): return
    
    feedString = FeedBusterUtils.fetchContent(feedUrl) 
    originSoup = BeautifulSoup.BeautifulStoneSoup(feedString, fromEncoding='utf-8', selfClosingTags=['media:content', 'media:thumbnail'])
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
    elif feedType == 'atom':
      def getLink(itemSoup): 
        retVal = itemSoup.find(["link"], rel="alternate", recursive=False)
        if not(retVal):
          retVal = itemSoup.find(["link"], rel=None, recursive=False)
        return retVal['href']
      soupParser = { 'items' : lambda feedSoup: feedSoup.channel.findAll(['entry'], recursive=False), 
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
      if processedItems >= 8:
        continue
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
        processedItems += 1
        
        #self.response.out.write("crawl0\n")
        if webScrape:
          linkNodeUrl = soupParser['link'](feedItem).string
          linkResultString = FeedBusterUtils.fetchContent(linkNodeUrl)
          scrapedMediaLinks = self.searchForMedia(linkResultString, webScrape)
          processedItems += 1
          #self.response.out.write("crawl1\n")
        else:
          #self.response.out.write("crawl2\n")
          contentNode = soupParser['content'](feedItem)
          if contentNode:
            content = "".join([unicode(j) for j in contentNode])
            scrapedMediaLinks = self.searchForMedia(content)
            #self.response.out.write("crawl3\n")
          if not(contentNode) or len(scrapedMediaLinks) == 0:
            descriptionCrawlNode = soupParser['description'](feedItem)
            if descriptionCrawlNode:
              descriptionSoup = "".join([unicode(j) for j in descriptionCrawlNode])
              scrapedMediaLinks = self.searchForMedia(descriptionSoup)
              #self.response.out.write(str(scrapedMediaLinks) + "crawl4\n")
              #self.response.out.write("crawl4\n")
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
      itemMedia['mediaLinks'] = filter(self.isAdvertising, itemMedia['mediaLinks'])
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
      
application = webapp.WSGIApplication([('/mediaInjection.*', MediaInjection), ('/cache.*', CacheControl), ('.*', Redirect)], debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()