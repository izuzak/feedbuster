import cgi
import os

import re
import urllib
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
  
  def get(self):
    requestParams = FeedBusterUtils.getRequestParams(self.request.url, ['inputFeedUrl']) 
    feedUrl = requestParams['inputFeedUrl']
    feedTree = FeedBusterUtils.fetchFeed(feedUrl)
    feedType = FeedBusterUtils.getFeedType(feedTree)

    if feedType == 'rss':
      parsingParams = { 'root' : 'channel', 'items' : 'item', 'crawlTags' : ['description', 'encoded', 'body', 'fullitem']}
    elif feedType == 'atom':
      parsingParams = { 'root' : 'feed', 'items' : 'entry', 'crawlTags' : ['summary', 'content']}
    else:
      return
    
    rootElem = feedTree.documentElement
    feedItems = xpath.find('//*[local-name() = "%s"]' % parsingParams['items'], rootElem)
    
    for feedItem in feedItems:
      mediaLinks = []
      nodesToCrawl = xpath.find('|'.join(['./*[local-name() = "%s"]' % crawlTag for crawlTag in parsingParams['crawlTags']]), feedItem)   
      for nodeToCrawl in nodesToCrawl:
        stringToParse = saxutils.unescape(nodeToCrawl.toxml(), {'&quot;' : '"'})
        imageTags = re.findall(r'(<img[^>]*? src=[\'"]{0,1}[^\'"]+["\'\s]{0,1}[^>]*?>)', stringToParse, re.IGNORECASE)
        for imageTag in imageTags:
          imageSrc = re.search(r'.*?src=[\'"]{0,1}([^\s\'"]+)["\'\s]{0,1}.*?', imageTag, re.IGNORECASE)
          imageWidth = re.search(r'.*?width=[\'"]{0,1}([^\s\'"]+)["\'\s]{0,1}.*?', imageTag, re.IGNORECASE)
          imageHeight = re.search(r'.*?height=[\'"]{0,1}([^\s\'"]+)["\'\s]{0,1}.*?', imageTag, re.IGNORECASE)
          if imageSrc:
            mediaLinks += [(imageSrc.group(1), imageWidth.group(1) if imageWidth else '100%' , imageHeight.group(1) if imageHeight else '100%' )]
      mediaLinks = set(mediaLinks)
      
      for mediaLink in mediaLinks:
        groupElem = feedTree.createElement('media:group')
        groupElem.setAttribute('xmlns:media','http://search.yahoo.com/mrss/')
        if mimetypes.guess_type(mediaLink[0])[0] != None:
          contentElem = feedTree.createElement('media:content')
          contentElem.setAttribute('url', mediaLink[0])
          contentElem.setAttribute('type', mimetypes.guess_type(mediaLink[0])[0])
          contentElem.setAttribute('width', mediaLink[1])
          contentElem.setAttribute('height', mediaLink[2])
          
          thumbElem = feedTree.createElement('media:thumbnail')
          thumbElem.setAttribute('url', mediaLink[0])
          thumbElem.setAttribute('width', mediaLink[1])
          thumbElem.setAttribute('height', mediaLink[2])
          
          feedItem.appendChild(groupElem)
          groupElem.appendChild(contentElem)
          groupElem.appendChild(thumbElem)

    self.response.headers['Content-Type'] = 'text/xml' 
    self.response.out.write(feedTree.toxml())
    return

class LanguageFilter(webapp.RequestHandler): 

  def get(self):
    return
      
application = webapp.WSGIApplication([('/mediaInjection.*', MediaInjection),
                                      ('/languageFilter.*', LanguageFilter)], debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()