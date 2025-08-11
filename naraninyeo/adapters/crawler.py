from typing import List, Optional
from bs4 import BeautifulSoup
from crawl4ai import AsyncLoggerBase, AsyncWebCrawler, PruningContentFilter, CrawlerRunConfig, DefaultMarkdownGenerator, RelevantContentFilter
from loguru import logger
import numpy as np
from naraninyeo.adapters.clients import EmbeddingClient

class LoggerWrapper(AsyncLoggerBase):
    def debug(self, message: str, tag: str = "DEBUG", **kwargs):
        logger.debug(f"{tag}: {message}", **kwargs)

    def info(self, message: str, tag: str = "INFO", **kwargs):
        logger.info(f"{tag}: {message}", **kwargs)

    def success(self, message: str, tag: str = "SUCCESS", **kwargs):
        logger.success(f"{tag}: {message}", **kwargs)

    def warning(self, message: str, tag: str = "WARNING", **kwargs):
        logger.warning(f"{tag}: {message}", **kwargs)

    def error(self, message: str, tag: str = "ERROR", **kwargs):
        logger.error(f"{tag}: {message}", **kwargs)

    def url_status(self, url: str, success: bool, timing: float, tag: str = "FETCH", url_length: int = 100):
        logger.debug(f"{tag}: {url} - {'SUCCESS' if success else 'FAILURE'} ({timing:.2f}s, {url_length} chars)")

    def error_status(self, url: str, error: str, tag: str = "ERROR", url_length: int = 100):
        logger.error(f"{tag}: {url} - {error} ({url_length} chars)")

class Crawler:
    def __init__(self, embedding_client: EmbeddingClient):
        self.crawler = AsyncWebCrawler(logger=LoggerWrapper())
        self.embedding_client = embedding_client

    async def start(self):
        """
        Starts the crawler. This method is a placeholder for any initialization logic if needed.
        """
        logger.debug("Starting the crawler...")
        await self.crawler.start()
        logger.debug("Crawler started.")


    async def stop(self):
        """
        Stops the crawler. This method is a placeholder for any cleanup logic if needed.
        """
        logger.debug("Stopping the crawler...")
        await self.crawler.close()
        logger.debug("Crawler stopped.")


    async def get_markdowns_from_urls(self, urls: list[str]) -> list[str]:
        """
        Crawls given URLs and extracts the most relevant parts based on a query.

        Args:
            urls: The URLs to crawl.
            query: The query to find the relevant part.

        Returns:
            The most relevant part of the pages as a string.
        """
        filter = PruningContentFilter(threshold=1.0, threshold_type="dynamic")
        md_generator = DefaultMarkdownGenerator(content_filter=filter)
        config = CrawlerRunConfig(
            markdown_generator=md_generator,
            only_text=True,
            excluded_tags=["a"],
            page_timeout=10000
        )

        # Run the crawler with the given URL and configuration
        results = await self.crawler.arun_many(
            urls=urls,
            config=config
        )
        output = []
        for r in results:
            if r.success:
                output.append(r.markdown.fit_markdown)
            else:
                logger.error(f"Failed to crawl {r.url}: {r.error_message}")
                output.append("")
        return output