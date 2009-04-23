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
    paramIndexes.sort(key=lambda x:x[1])
    paramIndexes = [(param, paramIndexes[i][1] + len(paramIndexes[i][0]) + 1, len(requestUrl) if (i == (len(paramIndexes)-1)) else paramIndexes[i+1][1]-1)
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

  def searchForImages(self, nodesToCrawl):
    images = []
    for nodeToCrawl in nodesToCrawl:
      stringToParse = saxutils.unescape(nodeToCrawl.toxml(), {'&quot;' : '"'})
      imageTags = re.findall(r'(<img[^>]*? src=[\'"]{0,1}[^\'"]+["\'\s]{0,1}[^>]*?>)', stringToParse, re.IGNORECASE)
      for imageTag in imageTags:
        imageSrc = re.search(r'.*?src=[\'"]{0,1}([^\s\'"]+)["\'\s]{0,1}.*?', imageTag, re.IGNORECASE)
        imageWidth = re.search(r'.*?width=[\'"]{0,1}([^\s\'"]+)["\'\s]{0,1}.*?', imageTag, re.IGNORECASE)
        imageHeight = re.search(r'.*?height=[\'"]{0,1}([^\s\'"]+)["\'\s]{0,1}.*?', imageTag, re.IGNORECASE)
        images += [{'url' : imageSrc.group(1),
                   'width' : imageWidth.group(1) if imageWidth else '100%',
                   'height' : imageHeight.group(1) if imageHeight else '100%',
                   'type' : mimetypes.guess_type(imageSrc.group(1))[0]}]
    return images
  
  def createMediaNode(self, feedTree, mediaLink):
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
  
  def get(self):
    requestParams = FeedBusterUtils.getRequestParams(self.request.url, ['inputFeedUrl']) 
    feedUrl = requestParams['inputFeedUrl']
    feedTree = FeedBusterUtils.fetchFeed(feedUrl)
    feedType = FeedBusterUtils.getFeedType(feedTree)

    if feedType == 'rss':
      parsingParams = { 'items' : '//*[local-name() = "channel"]/*[local-name() = "item"]', 
                        'description' : '*[local-name() = "description"]',
                        'content' : '*[local-name() = "encoded"]'}
    elif feedType == 'atom':
      parsingParams = { 'items' : '/*[local-name() = "entry"]', 
                        'description' : '*[local-name() = "summary"]',
                        'content' : '*[local-name() = "content"]'}
    else:
      return
    
    feedItems = xpath.find(parsingParams['items'], feedTree.documentElement)
    crawledMedia = []
    for feedItem in feedItems:
      contentCrawlNodes = xpath.find(parsingParams['content'], feedItem)
      contentMediaLinks = self.searchForImages(contentCrawlNodes)
      descriptionCrawlNodes = xpath.find(parsingParams['description'], feedItem)
      descriptionMediaLinks = self.searchForImages(descriptionCrawlNodes)
      crawledMedia += [{'feedNode' : feedItem, 'mediaLinks' : contentMediaLinks if len(contentMediaLinks) > 0 else descriptionMediaLinks}]
    
    # count repeated links
    mediaCount = {}
    for itemMedia in crawledMedia:
      for mediaLink in itemMedia['mediaLinks']:
        mediaCount[mediaLink['url']] = mediaCount[mediaLink['url']]+1 if mediaCount.has_key(mediaLink['url']) else 0
    
    for itemMedia in crawledMedia:
      itemMedia['mediaLinks'] = filter(lambda x: x['type']!=None, itemMedia['mediaLinks'])
      itemMedia['mediaLinks'] = filter(lambda x: mediaCount[x['url']]<3, itemMedia['mediaLinks'])
      
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