import feedparser

from app.models.news import NewsItem

_FEED_URL = "https://www.espn.com/espn/rss/nfl/news"


class EspnRssAdapter:
    def fetch(self, limit: int = 25) -> list[NewsItem]:
        feed = feedparser.parse(_FEED_URL)
        return [
            NewsItem(
                title=entry.get("title", ""),
                summary=entry.get("summary", ""),
                link=entry.get("link", ""),
                published=entry.get("published"),
            )
            for entry in feed.entries[:limit]
        ]
