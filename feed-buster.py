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
    #optimize - stavi ih u parsingparams, ili jos bolje nekako kroz child nodes izbjegni xpath
    # spomeni http://code.google.com/p/py-dom-xpath/
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
      
      # delete thumbnails <ns0:thumbnail height="72" url="http://4.bp.blogspot.com/_wGr8njEWjtI/SeDiV_V2xgI/AAAAAAAACcQ/EoarbHv4g30/s72-c/+Easter+cute-food-easter-bunny-cake.jpg" width="72" xmlns:ns0="http://search.yahoo.com/mrss/" />
      # view-source:http://feed-buster.appspot.com/mediaInjection?inputFeedUrl=http://feeds2.feedburner.com/CakeWrecks?format=xml
      # <media:content url="http://www.youtube.com/v/IyCRJmerW1Q&amp;f=user_favorites&amp;c=ytapi-FriendFeed-FriendFeed-8e762i7n-0&amp;d=C3jWYyDXZCPRCne8EtVoKmD9LlbsOl3qUImVMV6ramM&amp;app=youtube_gdata" type="application/x-shockwave-flash" width="" height=""/>
      
      #<media:content url="http://www.youtube.com/v/IyCRJmerW1Q&amp;f=user_favorites&amp;c=ytapi-FriendFeed-FriendFeed-8e762i7n-0&amp;d=C3jWYyDXZCPRCne8EtVoKmD9LlbsOl3qUImVMV6ramM&amp;app=youtube_gdata" type="application/x-shockwave-flash" width="" height=""/>
    
		# http://docs.python.org/library/htmlparser.html
		# http://docs.python.org/library/htmllib.html#module-htmllib
		# http://www.crummy.com/software/BeautifulSoup/
		# http://code.google.com/p/html5lib/
		# http://groups.google.com/group/google-appengine/browse_thread/thread/63d7afda2ca17dc4/7e73696b46f70c54?lnk=gst&q=parse+html#7e73696b46f70c54
		# http://lethain.com/entry/2008/jun/09/deployment-scripts-with-beautifulsoup/
		# http://stackoverflow.com/questions/300445/how-to-unquote-a-urlencoded-unicode-string-in-python
		# http://blog.ianbicking.org/2008/03/30/python-html-parser-performance/
		# http://blog.ianbicking.org/2008/12/10/lxml-an-underappreciated-web-scraping-library/
		# http://blog.emmesdee.com/2008/08/more-google-app-engine-rss.html
		# http://stackoverflow.com/questions/138313/how-to-extract-img-src-title-and-alt-from-html-using-php
		# http://stackoverflow.com/questions/257409/download-image-file-from-the-html-page-source-using-python
		# http://stackoverflow.com/questions/326103/why-is-this-regex-returning-errors-when-i-use-it-to-fish-img-srcs-from-html

class LanguageFilter(webapp.RequestHandler): 

  def get(self):
    return
    #params = FeedBusterUtils.getRequestParams(self.request.url, ['inputFeedUrl', 'searchQuery'])
    #feedUrl = params['inputFeedUrl']
    #query = params['searchQuery']

    #fetchResult = urlfetch.fetch(feedUrl) 
    #feedXMLString = fetchResult.content
    #feedType = FeedBusterUtils.getFeedType(self, feedXMLString)
    
    #if feedType == 'rss':
    #  parsingParams = { 'items' : 'item', 'crawlTags' : ['description', '{http://purl.org/rss/1.0/modules/content/}encoded', 'body', 'fullitem', 'title']}
    #elif feedType == 'atom':
    #  parsingParams = { 'items' : '{http://www.w3.org/2005/Atom}entry', 'crawlTags' : ['{http://www.w3.org/2005/Atom}summary', '{http://www.w3.org/2005/Atom}content', '{http://www.w3.org/2005/Atom}title']}
    #else:
    #  return

    #feedTree = ElementTree.fromstring(feedXMLString)
    #items = feedTree.findall('.//' + parsingParams['items'])
    
    #for item in items: 
    #  #find title, description and content
    #  nodesToCrawl = []
    #  for crawlTag in parsingParams['crawlTags']:
    #    nodesToCrawl += item.findall('.//' + crawlTag)
    #  
    #  detectionItem = ''
    #  for nodeToCrawl in nodesToCrawl:
    #    stringToParse = saxutils.unescape(ElementTree.tostring(nodeToCrawl))
    #    detectionItem += stringToParse + '\n'
    #  #http://code.google.com/apis/ajaxlanguage/documentation/#fonje
    #  #http://ajax.googleapis.com/ajax/services/language/detect?v=1.0&q=dobar%20dan%20bok%20zagreb%20krevet%20jastuk
    #  detectionItem = detectionItem[0:1000]
    #  detectLangApiUrl = 'http://ajax.googleapis.com/ajax/services/language/detect?v=1.0&q=' + urllib.quote(detectionItem)
    #  detectLangResult = urlfetch.fetch(detectLangApiUrl) 
    #  detectLangString = detectLangResult.content
    #  detectLangString = detectLangString
    #  detectLang = simplejson.loads(str(detectLangString))
    #  
    #  if (detectLang['responseData']['isReliable']): #confidence
    #    lang = detectLang['responseData']['language']
    #    if (lang != query):
    #      item.clear()
    #      #feedTree.remove(item)
    #return
    #self.response.headers['Content-Type'] = 'text/xml' 
    #self.response.out.write(ElementTree.tostring(feedTree))
      
application = webapp.WSGIApplication([('/mediaInjection.*', MediaInjection),
                                      ('/languageFilter.*', LanguageFilter)], debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()