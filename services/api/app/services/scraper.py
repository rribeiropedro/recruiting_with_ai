from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from typing import Final

import httpx
from bs4 import BeautifulSoup

REALISTIC_USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

FAST_PATH_MIN_WORDS: Final[int] = 200
SLOW_PATH_MIN_WORDS: Final[int] = 50

JOB_TEXT_SELECTORS: Final[tuple[str, ...]] = (
    "[data-testid='jobDescription']",
    "[data-testid='job-description']",
    "[data-automation-id='jobPostingDescription']",
    "[data-qa='job-description']",
    "[data-qa='jobDescription']",
    "[itemprop='description']",
    ".job-description",
    ".jobDescription",
    "#job-description",
    "#jobDescription",
    "[class*='job-description']",
    "[class*='jobDescription']",
    "[class*='description']",
    "article",
    "main",
)

NOISE_LINE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"^(accept|reject|manage|allow|decline)( all)? cookies?$", re.IGNORECASE),
    re.compile(r"^cookie (policy|preferences|settings)$", re.IGNORECASE),
    re.compile(r"^privacy policy$", re.IGNORECASE),
    re.compile(r"^terms (of use|and conditions)$", re.IGNORECASE),
    re.compile(r"^skip to (main )?content$", re.IGNORECASE),
    re.compile(r"^share this job$", re.IGNORECASE),
    re.compile(r"^apply now$", re.IGNORECASE),
)

CAPTCHA_TERMS: Final[tuple[str, ...]] = (
    "captcha",
    "verify you are human",
    "verify that you are human",
    "are you a human",
    "security check",
)

LOGIN_WALL_TERMS: Final[tuple[str, ...]] = (
    "sign in",
    "sign-in",
    "log in",
    "login",
    "create an account",
)


@dataclass(frozen=True)
class ScrapeResult:
    raw_html: str
    raw_text: str
    method: str


class ScrapeError(Exception):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class JobScraper:
    async def scrape(self, url: str) -> ScrapeResult:
        fast_result = await self._fast_scrape(url)
        if fast_result and self._word_count(fast_result.raw_text) >= FAST_PATH_MIN_WORDS:
            self._raise_for_access_wall(fast_result.raw_text)
            return fast_result

        slow_result = await self._playwright_scrape(url)
        if slow_result:
            self._raise_for_access_wall(slow_result.raw_text)
            if self._word_count(slow_result.raw_text) >= SLOW_PATH_MIN_WORDS:
                return slow_result

        if fast_result:
            self._raise_for_access_wall(fast_result.raw_text)

        raise ScrapeError(f"Could not extract job description from {url}")

    async def _fast_scrape(self, url: str) -> ScrapeResult | None:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.get(url, headers={"User-Agent": REALISTIC_USER_AGENT})
        except httpx.HTTPError:
            return None

        if response.status_code == 404:
            raise ScrapeError(
                "Job posting not found - it may have been removed.",
                retryable=False,
            )
        if response.status_code >= 400:
            return None

        content_type = response.headers.get("content-type", "").lower()
        if "application/pdf" in content_type or url.lower().split("?", 1)[0].endswith(".pdf"):
            return ScrapeResult(
                raw_html="",
                raw_text=self._extract_pdf_text(response.content),
                method="pdf",
            )

        soup = BeautifulSoup(response.text, "html.parser")
        self._remove_noise_elements(soup)
        text = self._extract_job_text(soup)
        if not text:
            return None
        return ScrapeResult(raw_html=response.text, raw_text=text, method="httpx")

    async def _playwright_scrape(self, url: str) -> ScrapeResult | None:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return None

        browser = None
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=REALISTIC_USER_AGENT,
                    viewport={"width": 1280, "height": 800},
                )
                page = await context.new_page()
                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                await page.goto(url, wait_until="networkidle", timeout=30_000)
                html = await page.content()
                text = await page.inner_text("body", timeout=5_000)
                await context.close()
                await browser.close()
                browser = None
        except Exception:
            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    pass
            return None

        return ScrapeResult(raw_html=html, raw_text=self._clean_text(text), method="playwright")

    def _extract_job_text(self, soup: BeautifulSoup) -> str:
        for selector in JOB_TEXT_SELECTORS:
            element = soup.select_one(selector)
            if not element:
                continue
            text = self._clean_text(element.get_text(separator="\n", strip=True))
            if self._word_count(text) >= SLOW_PATH_MIN_WORDS:
                return text
        return self._clean_text(soup.get_text(separator="\n", strip=True))

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\r\n?", "\n", text)
        lines: list[str] = []
        previous = ""

        for raw_line in text.split("\n"):
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            if any(pattern.match(line) for pattern in NOISE_LINE_PATTERNS):
                continue
            if line == previous:
                continue
            lines.append(line)
            previous = line

        return "\n".join(lines).strip()

    def _remove_noise_elements(self, soup: BeautifulSoup) -> None:
        for tag in soup.find_all(
            [
                "aside",
                "footer",
                "form",
                "header",
                "iframe",
                "nav",
                "noscript",
                "script",
                "style",
                "svg",
            ]
        ):
            tag.decompose()

    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        try:
            import pdfplumber
        except ImportError as exc:
            message = "PDF extraction dependency is not installed."
            raise ScrapeError(message, retryable=False) from exc

        try:
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception as exc:
            raise ScrapeError("Could not extract text from job posting PDF.") from exc

        cleaned = self._clean_text(text)
        if not cleaned:
            raise ScrapeError("Could not extract text from job posting PDF.", retryable=False)
        return cleaned

    def _raise_for_access_wall(self, text: str) -> None:
        lowered = text.lower()
        word_count = self._word_count(text)

        if word_count < FAST_PATH_MIN_WORDS and any(term in lowered for term in CAPTCHA_TERMS):
            raise ScrapeError(
                "CAPTCHA detected - please paste the job description manually.",
                retryable=False,
            )
        if word_count < SLOW_PATH_MIN_WORDS and any(term in lowered for term in LOGIN_WALL_TERMS):
            raise ScrapeError(
                "This page requires login - please paste the job description.",
                retryable=False,
            )

    def _word_count(self, text: str) -> int:
        return len(re.findall(r"\b[\w+#.-]+\b", text))


job_scraper = JobScraper()
