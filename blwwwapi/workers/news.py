#!/usr/bin/env python3

from blwwwapi.workers.base import WorkerBase
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from django.utils import feedgenerator
from typing import List
import datetime
import feedparser
import requests
import time
import uuid

class News(WorkerBase):
  _id = "feed"
  __feed_guid = str(uuid.uuid5(uuid.NAMESPACE_DNS, "forums.bunsenlabs.org"))

  def main(self):
    self._announcement_url = "{base_url}/extern.php?action=feed&fid=12&type=atom".format(
        base_url=self._settings.FORUM_URL)
    self._info_forum_url = "{base_url}/viewforum.php?id=12".format(
        base_url=self._settings.FORUM_URL)
    self.update_feed_data()
    while not self._waiter.wait(timeout=self._settings.NEWS_UPDATE_INTERVAL):
      if self.is_stopped():
        return
      self.update_feed_data()
    return 0

  def retrieve_op_data(self, entry) -> dict:
    topic_url = entry['link'].split("&")[0]
    text = ""
    date = "1999-01-01"
    fulltext = ""
    try:
      body = requests.get(topic_url).text
      soup = BeautifulSoup(body, "html.parser")
      op = soup.find("div", { "class": "blockpost1" })
      # Summary
      p = op.find("div", { "class":"postmsg"}).find("p")
      for br in p.findAll("br"):
        br.replace_with(' ')
      text = p.prettify(formatter="html")
      # Full text
      fulltext = op.find("div", { "class":"postmsg"}).prettify(formatter="html")
      date = op.find("h2").find("a").text
      date = date.split(" ")[0]
      if "Today" in date:
        date = date.replace("Today", datetime.datetime.utcnow().strftime("%Y-%m-%d"))
      elif "Yesterday" in date:
        date = date.replace("Yesterday", (datetime.datetime.utcnow() - datetime.timedelta(days=1)).strftime("%Y-%m-%d"))
    except BaseException as e:
      self.error(e)
      self.error(f"topic_url={topic_url}, text={text}, date={date}")
    finally:
      return { "updated": date, "summary": text, "fulltext": fulltext }

  def update_feed_data(self) -> None:
    json_entries = []
    entry_data = None

    feed = feedparser.parse(self._announcement_url)
    refeed = feedgenerator.Atom1Feed(
        'BunsenLabs Linux News',
        self._info_forum_url,
        "",
        feed_guid=self.__feed_guid)

    with ThreadPoolExecutor(max_workers=4) as executor:
      for entry, entry_data in zip(feed.entries,
          executor.map(self.retrieve_op_data, feed.entries)):

          title = " ".join(entry['title'].split())
          link = self.head(entry['link'], '&')
          date = self.head(entry['updated'], 'T')
          updated = entry_data['updated']
          op_summary = entry_data['summary']
          fulltext = entry_data['fulltext']
          unique_id = str(uuid.uuid5(uuid.NAMESPACE_URL, link))

          self.log("News item {uuid} updated {updated} ({title})".format(
            uuid=unique_id,title = title, updated=updated))

          refeed.add_item(
              title,
              link,
              fulltext,
              updateddate = datetime.datetime.strptime(updated, "%Y-%m-%d"),
              unique_id = unique_id
          )

          json_entries.append({ "link": link, "date": date, "updated": updated, "op_summary": op_summary, "title": title })

    json_entries = sorted(json_entries, key=lambda e: e['updated'], reverse=True)
    self.emit(payload = {
      "endpoint": "/feed/news",
      "data": { "entries": json_entries, "ts": int(time.time()) }
    })

    self.emit(payload = {
      "endpoint": "/feed/news/atom",
      "data": refeed.writeString("utf-8")
    })

  @staticmethod
  def head(s: str, sep: str) -> List[str]:
    return s.split(sep)[0]
