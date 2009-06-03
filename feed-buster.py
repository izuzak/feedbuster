import cgi
import os
import re
import urllib
import urlparse
import mimetypes
import xpath
import BeautifulSoup

import math
from xml.sax import saxutils 
from django.utils import simplejson 
from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.api.urlfetch import DownloadError 
from google.appengine.ext import webapp
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
  def fetchContentJSON(contentUrl):
    contentString = FeedBusterUtils.fetchContent(contentUrl)
    return simplejson.loads(contentString)
  
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