import cgi
import os
import re
import urllib
import urlparse
import mimetypes
import xpath

from xml.dom import minidom
from xml.etree import ElementTree 
from xml.sax import saxutils 
from django.utils import simplejson 
from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

class FeedBusterUtils():
  @staticmethod
  def getRequestParams(requestUrl, paramsList):
    paramIndexes = [(param, requestUrl.find(param)) for param in paramsList]
    paramIndexes = filter(lambda x: x[1]!=-1, paramIndexes)
    paramIndexes.sort(key=lambda x:x[1])
    paramIndexes = [(paramIndexes[i][0], paramIndexes[i][1] + len(paramIndexes[i][0]) + 1, len(requestUrl) if (i == (len(paramIndexes)-1)) else paramIndexes[i+1][1]-1)
                    for i in range(len(paramIndexes))]
    return dict((param[0], urllib.unquote(requestUrl[param[1]:param[2]])) for param in paramIndexes)

  @staticmethod
  def fetchContent(contentUrl):
    contentUrl = contentUrl.replace(" ", "%20")
    fetchResult = urlfetch.fetch(contentUrl) 
    if fetchResult.status_code != 200:
      return None
    contentString = fetchResult.content
    return contentString
  
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
  def storeData(key, data):
    return memcache.set(key, data)
  
  @staticmethod
  def getData(key):
    return memcache.get(key)
      
class ClearCache(webapp.RequestHandler):
  def get(self):
    return str(memcache.flush_all())

class MediaInjection(webapp.RequestHandler): 

  # simple api - http://vimeo.com/api/clip/2539741.json
  # advanced api - vimeo.videos.getThumbnailUrl
  def getVimeoThumbnail(self, vimeoVideoId):
    vimeoApiCallUrl = 'http://vimeo.com/api/clip/%s.json' % vimeoVideoId
    vimeoApiResponseJson = FeedBusterUtils.fetchContentJSON(vimeoApiCallUrl)
    return vimeoApiResponseJson[0]['thumbnail_large'].replace('\\','')
    
  def maxResizeImage(self, imageWidth, imageHeight):
    #todo - switch to default params
    ffImageMaxWidth = 525
    ffImageMaxHeight = 175
    
    if imageWidth < ffImageMaxWidth and imageHeight < ffImageMaxHeight:
      return imageWidth, imageHeight
    else:
      widthReduction = imageWidth/ffImageMaxWidth
      heightReduction = imageHeight/ffImageMaxHeight
      reduction =  widthReduction if widthReduction > heightReduction else heightReduction
      return imageWidth/reduction, imageHeight/reduction,

  def getImageProperties(self, imageUrl):
    # check memcached
    #imageInfo = memcache.get(imageUrl)
    imageInfo=None
    # invoke IMG2JSON AppEngine Service
    if imageInfo is None:
      serviceCallUrl = 'http://img2json.appspot.com/go/?url='+imageUrl
      serviceResultJson = FeedBusterUtils.fetchContent(serviceCallUrl) 
      imageInfo = simplejson.loads(serviceResultJson.replace("'",'"').replace(";","")) if serviceResultJson else None
      if imageInfo is None or imageInfo.has_key('error'):
        imageInfo = None
      else:
        imageInfo = { 'width' : str(imageInfo['width']), 'height' : str(imageInfo['height']), 'mimeType' : imageInfo['mimeType'] }
    return imageInfo
    
  def setImageProperties(self, imageUrl, imageInfo):
    memcache.set(imageUrl, imageInfo, 3600*2)
    return

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
                  'thumb' : 'http://friendfeed.com/static/images/film.png?v=d0719a0e04c5eafb9ab6895204fc5b0d', #TODO: fetch thumb from vimeo api
                  'thumbWidth' : '130',
                  'thumbHeight' : '97',
                  'type' : 'application/x-shockwave-flash'}]
    #video - youtube
    videoTags = re.findall(r'(<embed[^>]*? src=[\'"]{0,1}[^\'"]+?youtube\.com/v/[^\'"]+?["\'\s]{0,1}[^>]*?>)', stringToParse, re.IGNORECASE)
    for videoTag in videoTags:
      videoId = re.search(r'.*?src=[\'"]{0,1}[^\'"]+?youtube.com/v/([^\'"#&?\s;]+)[^\'"]+?["\'\s]{0,1}.*?', videoTag, re.IGNORECASE)
      videoId = videoId.group(1)
      videos += [{'mediaType' : 'vid',
                  'url' : 'http://www.youtube.com/v/' + videoId,
                  'thumb' : 'http://img.youtube.com/vi/' + videoId + '/2.jpg',
                  'thumbWidth' : '130',
                  'thumbHeight' : '97',
                  'type' : 'application/x-shockwave-flash'}]
		
		# TODO: video - flickr
		#<object type="application/x-shockwave-flash" width="500" height="375" data="http://www.flickr.com/apps/video/stewart.swf?v=71377" classid="clsid:D27CDB6E-AE6D-11cf-96B8-444553540000">
		#	<param name="flashvars" value="intl_lang=en-us&#038;photo_secret=0cd85ca6c8&#038;photo_id=3473039350"></param>
		#	<param name="movie" value="http://www.flickr.com/apps/video/stewart.swf?v=71377"></param>
		#	<param name="bgcolor" value="#000000"></param><param name="allowFullScreen" value="true"></param>
		#	<embed type="application/x-shockwave-flash" src="http://www.flickr.com/apps/video/stewart.swf?v=71377" bgcolor="#000000" allowfullscreen="true" flashvars="intl_lang=en-us&#038;photo_secret=0cd85ca6c8&#038;photo_id=3473039350" height="375" width="500"></embed>
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

      #self.setImageProperties(imageSrc, { 'width' : imageWidth, 'height' : imageHeight, 'mimeType' : imageType })
      images += [{'mediaType' : 'img', 'url' : imageSrc, 'width' : imageWidth, 'height' : imageHeight, 'type' : imageType}]
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
  
  def adsBlacklist(self, url):
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
     
  def get(self):
    requestParams = FeedBusterUtils.getRequestParams(self.request.url, ['inputFeedUrl', 'webScrape']) 
    feedUrl = requestParams['inputFeedUrl']
    webScrape = requestParams['webScrape'] if requestParams.has_key('webScrape') else None
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
      if feedItemIndex >= 15:
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
      # repeated media
      itemMedia['mediaLinks'] = filter(lambda x: mediaCount[x['url']]<3, itemMedia['mediaLinks'])
      # small images
      itemMedia['mediaLinks'] = filter(self.isSmallImage, itemMedia['mediaLinks'])
      #ads
      itemMedia['mediaLinks'] = filter(self.adsBlacklist, itemMedia['mediaLinks'])

    #generate media enclosure XML elements
    for itemMedia in crawledMedia:
      feedItem = itemMedia['feedNode']
      media = itemMedia['mediaLinks']
      memcache.set(itemMedia['cacheId'], {'itemHash' : itemMedia['itemHash'], 'crawledMedia' : media})
      for mediaLink in media:
        mediaElem = self.createMediaNode(feedTree, mediaLink)
        feedItem.appendChild(mediaElem)
	  
		# write output feed
    self.response.headers['Content-Type'] = 'application/%s+xml' % feedType
    self.response.out.write(feedTree.toxml())
    return
      
application = webapp.WSGIApplication([('/mediaInjection.*', MediaInjection), ('/clearCache.*', ClearCache)], debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()