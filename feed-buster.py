import cgi
import os
import feedparser

from xml.dom import minidom

from google.appengine.api import urlfetch

from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

class MediaInjection(webapp.RequestHandler): 

  def get(self):
    feedUrl = self.request.get('inputFeedUrl')

    # fetch feed XML string
    fetchResult = urlfetch.fetch(feedUrl) 
    
    #check if fetched ok
    if fetchResult.status_code != 200:
      self.response.out.write("invalidu!")
      return
    
    feedXMLString = fetchResult.content
    feed = feedparser.parse(feedXMLString)
    
    for entry in feed.entries:
      if entry.has_key('summary'):
        self.response.out.write(entry.content[0].value + '\n')
        
    # >>> e.enclosures[0]
    # {'type': u'audio/mpeg',
    # 'length': u'1069871',
    # 'href': u'http://example.org/audio/demo.mp3'}

    
    # parse feed XML into DOM
    # feedXMLString = fetchResult.content
    # feedDOM = minidom.parseString(feedXMLString) 
    
    #self.response.out.write(feedDOM.toxml())
    
    # contentElements = feedDOM.getElementsByTagName("description")
    # for content in contentElements:
    #  self.response.out.write(content.toxml() + "\n")
      
    # pokupi sve slike iz summarya i contenta, izbaci duplikate
    # problem sa namespaceima ns:item
    
    #check if rss or atom
    
    #extract media info
    
    #generate media items
    
    #insert items into feed
    
    # self.response.out.write(feedXMLString)

application = webapp.WSGIApplication([('/mediaInjection.*', MediaInjection)], debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()