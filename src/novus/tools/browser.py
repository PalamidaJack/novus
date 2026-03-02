"""
Browser automation toolkit for NOVUS.

Enables agents to interact with websites, extract data, and perform web actions.
Inspired by CAMEL-AI's BrowserToolkit.
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urljoin, urlparse
import structlog

try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    
logger = structlog.get_logger()


@dataclass
class BrowserAction:
    """A browser action to perform."""
    action_type: str  # navigate, click, type, scroll, extract, screenshot
    selector: Optional[str] = None
    value: Optional[str] = None
    url: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BrowserObservation:
    """Result of a browser observation."""
    url: str
    title: str
    content: str
    links: List[Dict[str, str]] = field(default_factory=list)
    forms: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class BrowserSession:
    """A browser session with history."""
    session_id: str
    start_url: str
    history: List[BrowserObservation] = field(default_factory=list)
    actions_taken: List[BrowserAction] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


class BrowserToolkit:
    """
    Browser automation toolkit for web interaction.
    
    Features:
    - Page navigation
    - Element interaction (click, type)
    - Data extraction
    - Form filling
    - Screenshots
    - Session management
    - History tracking
    """
    
    def __init__(
        self,
        headless: bool = True,
        slow_mo: int = 0,
        viewport: Optional[Dict[str, int]] = None,
        user_agent: Optional[str] = None
    ):
        self.headless = headless
        self.slow_mo = slow_mo
        self.viewport = viewport or {"width": 1280, "height": 720}
        self.user_agent = user_agent
        
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._sessions: Dict[str, BrowserSession] = {}
        
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("playwright_not_installed", 
                         message="Install with: pip install playwright && playwright install")
    
    async def start(self) -> None:
        """Start the browser."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright not installed")
        
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo
        )
        
        context_options = {
            "viewport": self.viewport
        }
        if self.user_agent:
            context_options["user_agent"] = self.user_agent
        
        self._context = await self._browser.new_context(**context_options)
        self._page = await self._context.new_page()
        
        logger.info("browser_started", headless=self.headless)
    
    async def stop(self) -> None:
        """Stop the browser."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("browser_stopped")
    
    async def navigate(self, url: str) -> BrowserObservation:
        """Navigate to a URL."""
        if not self._page:
            await self.start()
        
        logger.info("navigating", url=url)
        
        try:
            response = await self._page.goto(url, wait_until="networkidle")
            
            # Extract page information
            observation = await self._extract_observation()
            
            logger.info("navigation_complete", 
                       url=observation.url, 
                       title=observation.title,
                       status=response.status if response else None)
            
            return observation
            
        except Exception as e:
            logger.error("navigation_error", url=url, error=str(e))
            raise
    
    async def click(self, selector: str, timeout: int = 5000) -> BrowserObservation:
        """Click an element."""
        logger.info("clicking_element", selector=selector)
        
        await self._page.click(selector, timeout=timeout)
        await self._page.wait_for_load_state("networkidle")
        
        return await self._extract_observation()
    
    async def type_text(
        self, 
        selector: str, 
        text: str, 
        clear_first: bool = True,
        submit: bool = False
    ) -> BrowserObservation:
        """Type text into an input field."""
        logger.info("typing_text", selector=selector, text=text[:50])
        
        if clear_first:
            await self._page.fill(selector, "")
        
        await self._page.type(selector, text)
        
        if submit:
            await self._page.press(selector, "Enter")
            await self._page.wait_for_load_state("networkidle")
        
        return await self._extract_observation()
    
    async def extract_text(self, selector: Optional[str] = None) -> str:
        """Extract text from page or element."""
        if selector:
            element = await self._page.query_selector(selector)
            if element:
                return await element.inner_text()
            return ""
        
        return await self._page.inner_text("body")
    
    async def extract_structured(
        self, 
        selectors: Dict[str, str]
    ) -> Dict[str, str]:
        """
        Extract structured data using CSS selectors.
        
        Args:
            selectors: Dict mapping field names to CSS selectors
            
        Returns:
            Dict with extracted values
        """
        result = {}
        
        for field_name, selector in selectors.items():
            try:
                element = await self._page.query_selector(selector)
                if element:
                    result[field_name] = await element.inner_text()
                else:
                    result[field_name] = None
            except Exception as e:
                logger.warning("extraction_error", field=field_name, error=str(e))
                result[field_name] = None
        
        return result
    
    async def extract_links(self) -> List[Dict[str, str]]:
        """Extract all links from the page."""
        links = await self._page.query_selector_all("a[href]")
        result = []
        
        for link in links:
            try:
                href = await link.get_attribute("href")
                text = await link.inner_text()
                
                if href:
                    # Resolve relative URLs
                    absolute_url = urljoin(self._page.url, href)
                    result.append({
                        "text": text.strip()[:100] if text else "",
                        "url": absolute_url
                    })
            except:
                continue
        
        return result
    
    async def extract_forms(self) -> List[Dict[str, Any]]:
        """Extract form structures from the page."""
        forms = await self._page.query_selector_all("form")
        result = []
        
        for form in forms:
            try:
                form_data = {
                    "action": await form.get_attribute("action"),
                    "method": await form.get_attribute("method") or "get",
                    "inputs": []
                }
                
                inputs = await form.query_selector_all("input, textarea, select")
                for input_el in inputs:
                    input_data = {
                        "type": await input_el.get_attribute("type") or "text",
                        "name": await input_el.get_attribute("name"),
                        "id": await input_el.get_attribute("id"),
                        "placeholder": await input_el.get_attribute("placeholder"),
                        "required": await input_el.get_attribute("required") is not None
                    }
                    form_data["inputs"].append(input_data)
                
                result.append(form_data)
            except:
                continue
        
        return result
    
    async def scroll(self, direction: str = "down", amount: int = 500) -> None:
        """Scroll the page."""
        if direction == "down":
            await self._page.evaluate(f"window.scrollBy(0, {amount})")
        elif direction == "up":
            await self._page.evaluate(f"window.scrollBy(0, -{amount})")
        elif direction == "bottom":
            await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        elif direction == "top":
            await self._page.evaluate("window.scrollTo(0, 0)")
    
    async def screenshot(self, path: Optional[str] = None) -> bytes:
        """Take a screenshot."""
        if path:
            await self._page.screenshot(path=path, full_page=True)
            logger.info("screenshot_saved", path=path)
        
        return await self._page.screenshot(full_page=True)
    
    async def wait_for_selector(
        self, 
        selector: str, 
        timeout: int = 5000,
        state: str = "visible"
    ) -> bool:
        """Wait for an element to appear."""
        try:
            await self._page.wait_for_selector(
                selector, 
                timeout=timeout,
                state=state
            )
            return True
        except:
            return False
    
    async def search_on_page(self, query: str) -> List[Dict[str, Any]]:
        """Search for text on the page."""
        # Use JavaScript to find text
        script = """
        (query) => {
            const results = [];
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                null,
                false
            );
            
            let node;
            while (node = walker.nextNode()) {
                if (node.textContent.toLowerCase().includes(query.toLowerCase())) {
                    const element = node.parentElement;
                    results.push({
                        text: node.textContent.trim().substring(0, 200),
                        tag: element.tagName,
                        id: element.id,
                        class: element.className
                    });
                }
            }
            return results;
        }
        """
        
        return await self._page.evaluate(script, query)
    
    async def _extract_observation(self) -> BrowserObservation:
        """Extract current page state."""
        url = self._page.url
        title = await self._page.title()
        
        # Get visible text content
        content = await self._extract_main_content()
        
        # Get links
        links = await self.extract_links()
        
        # Get forms
        forms = await self.extract_forms()
        
        return BrowserObservation(
            url=url,
            title=title,
            content=content,
            links=links[:50],  # Limit links
            forms=forms
        )
    
    async def _extract_main_content(self) -> str:
        """Extract main content, removing navigation and ads."""
        # Try common content selectors
        content_selectors = [
            "article",
            "main",
            "[role='main']",
            ".content",
            "#content",
            ".post-content",
            ".entry-content"
        ]
        
        for selector in content_selectors:
            try:
                element = await self._page.query_selector(selector)
                if element:
                    return await element.inner_text()
            except:
                continue
        
        # Fallback to body text
        return await self._page.inner_text("body")
    
    async def execute_action_sequence(
        self, 
        actions: List[BrowserAction]
    ) -> List[BrowserObservation]:
        """Execute a sequence of browser actions."""
        observations = []
        
        for action in actions:
            try:
                if action.action_type == "navigate":
                    obs = await self.navigate(action.url)
                elif action.action_type == "click":
                    obs = await self.click(action.selector)
                elif action.action_type == "type":
                    obs = await self.type_text(
                        action.selector, 
                        action.value,
                        submit=action.options.get("submit", False)
                    )
                elif action.action_type == "scroll":
                    await self.scroll(
                        action.options.get("direction", "down"),
                        action.options.get("amount", 500)
                    )
                    obs = await self._extract_observation()
                elif action.action_type == "extract":
                    obs = await self._extract_observation()
                else:
                    obs = await self._extract_observation()
                
                observations.append(obs)
                
            except Exception as e:
                logger.error("action_failed", action=action.action_type, error=str(e))
                observations.append(BrowserObservation(
                    url=self._page.url if self._page else "",
                    title="Error",
                    content=f"Action failed: {str(e)}"
                ))
        
        return observations
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get tool definitions for agent integration."""
        return [
            {
                "name": "browser_navigate",
                "description": "Navigate to a URL",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to navigate to"}
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "browser_click",
                "description": "Click an element on the page",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS selector"}
                    },
                    "required": ["selector"]
                }
            },
            {
                "name": "browser_type",
                "description": "Type text into an input field",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string"},
                        "text": {"type": "string"},
                        "submit": {"type": "boolean"}
                    },
                    "required": ["selector", "text"]
                }
            },
            {
                "name": "browser_extract",
                "description": "Extract information from the page",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selectors": {
                            "type": "object",
                            "description": "Map of field names to CSS selectors"
                        }
                    }
                }
            },
            {
                "name": "browser_search",
                "description": "Search for text on the page",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"}
                    },
                    "required": ["query"]
                }
            }
        ]


# Convenience function for quick web searches
async def quick_web_search(query: str, num_results: int = 5) -> List[Dict[str, str]]:
    """
    Perform a quick web search using the browser toolkit.
    
    This is a simplified interface for common use cases.
    """
    toolkit = BrowserToolkit(headless=True)
    
    try:
        await toolkit.start()
        
        # Navigate to search engine
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        await toolkit.navigate(search_url)
        
        # Extract search results
        results = await toolkit.extract_structured({
            "results": "#search .g"
        })
        
        # Get links
        links = await toolkit.extract_links()
        
        return links[:num_results]
        
    finally:
        await toolkit.stop()


# Example usage
if __name__ == "__main__":
    async def example():
        toolkit = BrowserToolkit(headless=False)  # Visible for demo
        
        try:
            await toolkit.start()
            
            # Navigate and extract
            obs = await toolkit.navigate("https://example.com")
            print(f"Title: {obs.title}")
            print(f"Content preview: {obs.content[:500]}")
            print(f"Found {len(obs.links)} links")
            
            # Take screenshot
            await toolkit.screenshot("example.png")
            
        finally:
            await toolkit.stop()
    
    asyncio.run(example())
