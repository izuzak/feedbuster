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
  def fetchFeed(feedUrl):
    feedUrl = feedUrl.replace(" ", "%20")
    fetchResult = urlfetch.fetch(feedUrl) 
    if fetchResult.status_code != 200:
      return None
    feedXMLString = fetchResult.content
    return minidom.parseString(feedXMLString)
    
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

class MediaInjection(webapp.RequestHandler): 

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
                  'thumb' : 'http://friendfeed.com/static/images/film.png?v=d0719a0e04c5eafb9ab6895204fc5b0d',
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
    # images
    imageTags = re.findall(r'(<img[^>]*?\ssrc=[\'"]{0,1}[^\'"]+["\'\s]{0,1}[^>]*?>)', stringToParse, re.IGNORECASE)
    for imageTag in imageTags:
      imageSrc = re.search(r'.*?src=[\'"]{0,1}([^\s\'"]+)["\'\s]{0,1}.*?', imageTag, re.IGNORECASE)
      imageWidth = re.search(r'.*?width=[\'"]{0,1}(\d+%?)["\'\s]{0,1}.*?', imageTag, re.IGNORECASE)
      imageHeight = re.search(r'.*?height=[\'"]{0,1}(\d+%?)["\'\s]{0,1}.*?', imageTag, re.IGNORECASE)
      images += [{'mediaType' : 'img',
                  'url' : imageSrc.group(1),
                  'width' : imageWidth.group(1) if imageWidth else '175',
                  'height' : imageHeight.group(1) if imageHeight else '175',
                  'type' : mimetypes.guess_type(imageSrc.group(1))[0]}]
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
    
  def isSmallImage(self, mediaItem):
    if mediaItem['mediaType']=='img':
      if mediaItem.has_key('width') and mediaItem.has_key('height'):
        if int(mediaItem['width'].replace("%", "")) < 15 or int(mediaItem['height'].replace("%", "")) < 15:
          return False
        else:
          return True
      else:
        return True
    return True 
     
  def get(self):
    requestParams = FeedBusterUtils.getRequestParams(self.request.url, ['inputFeedUrl', 'linkScrapeXpath']) 
    feedUrl = requestParams['inputFeedUrl']
    linkScrapeXpath = requestParams['linkScrapeXpath'] if requestParams.has_key('linkScrapeXpath') else None
    feedTree = FeedBusterUtils.fetchFeed(feedUrl)
    feedType = FeedBusterUtils.getFeedType(feedTree)

    if feedType == 'rss':
      parsingParams = { 'items' : '//*[local-name() = "channel"]/*[local-name() = "item"]', 
                        'link' : '*[local-name() = "link"]/node()',
                        'description' : '*[local-name() = "description"]',
                        'content' : '*[local-name() = "encoded"]'}
    elif feedType == 'atom':
      parsingParams = { 'items' : '//*[local-name() = "entry"]', 
                        'link' : '*[local-name() = "link" and (@rel="alternate" or not(@rel))]/@href',
                        'description' : '*[local-name() = "summary"]',
                        'content' : '*[local-name() = "content"]'}
    else:
      return

    feedItems = xpath.find(parsingParams['items'], feedTree.documentElement)
    crawledMedia = []
    for feedItem in feedItems:
      if linkScrapeXpath:
        linkNode = xpath.find(parsingParams['link'], feedItem)[0]
        linkUrl = linkNode.nodeValue
        linkUrl = urllib.unquote(linkUrl).replace(" ", "%20")
        linkResult = urlfetch.fetch(linkUrl) 
        if linkResult.status_code != 200:
          return None
        linkResultString = linkResult.content
        scrapedMediaLinks = self.searchForMediaString(linkResultString)
        crawledMedia += [{'feedNode' : feedItem, 'mediaLinks' : scrapedMediaLinks}]
      else:
        contentCrawlNodes = xpath.find(parsingParams['content'], feedItem)
        contentMediaLinks = self.searchForMediaDOM(contentCrawlNodes)
        descriptionCrawlNodes = xpath.find(parsingParams['description'], feedItem)
        descriptionMediaLinks = self.searchForMediaDOM(descriptionCrawlNodes)
        crawledMedia += [{'feedNode' : feedItem, 'mediaLinks' : contentMediaLinks if len(contentMediaLinks) > 0 else descriptionMediaLinks}]
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
    for itemMedia in crawledMedia:
      feedItem = itemMedia['feedNode']
      media = itemMedia['mediaLinks']
      for mediaLink in media:
        mediaElem = self.createMediaNode(feedTree, mediaLink)
        feedItem.appendChild(mediaElem)
    self.response.headers['Content-Type'] = 'text/xml' 
    self.response.out.write(feedTree.toxml())
    return
      
application = webapp.WSGIApplication([('/mediaInjection.*', MediaInjection)], debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()