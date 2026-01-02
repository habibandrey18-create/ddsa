# utils/yandex_market_link_gen.py
"""
YandexMarketLinkGen - Production-ready async implementation
Network-first approach with XHR reproduction, stealth, and circuit breaker
"""
import logging

from .link_gen.main_generator import YandexMarketLinkGen

logger = logging.getLogger(__name__)

# Re-export the main class for backward compatibility
__all__ = ['YandexMarketLinkGen']
    
    def _get_storage_state_path(self, url: str) -> Optional[Path]:
        """
        Get storage state path for reuse based on URL domain.
        Returns path if exists, None otherwise.
        """
        try:
            # Убеждаемся, что директория существует
            STORAGE_STATE_DIR.mkdir(exist_ok=True, parents=True)
            domain = urlparse(url).netloc
            fingerprint = hash(domain) % STORAGE_STATE_HASH_MOD
            state_path = STORAGE_STATE_DIR / f"{fingerprint}.json"
            if state_path.exists():
                return state_path
        except Exception:
            pass
        return None
    
    async def _save_debug_artifacts(
        self,
        page,
        job_id: str,
        error_msg: str = "",
        xhr_info: Optional[Dict] = None
    ):
        """
        Save debug artifacts on failure.
        Always attempts to save, even if page is partially initialized.
        """
        if not self.debug:
            return
        
        saved_artifacts = []
        
        try:
            # Убеждаемся, что директория существует
            DEBUG_DIR.mkdir(exist_ok=True, parents=True)
            # HTML - try to save even if page is not fully loaded
            html_path = DEBUG_DIR / f"{job_id}.html"
            try:
                if page:
                    html_content = await asyncio.wait_for(
                        page.content(),
                        timeout=5.0
                    )
                    html_path.write_text(html_content, encoding="utf-8")
                    saved_artifacts.append("HTML")
                    logger.info(f"💾 Saved HTML: {html_path}")
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ HTML save timeout for {job_id}")
            except Exception as e:
                logger.warning(f"Failed to save HTML: {e}")
            
            # Screenshot - try to save even if page is not fully loaded
            screenshot_path = DEBUG_DIR / f"{job_id}.png"
            try:
                if page:
                    await asyncio.wait_for(
                        page.screenshot(path=str(screenshot_path), full_page=True),
                        timeout=5.0
                    )
                    saved_artifacts.append("screenshot")
                    logger.info(f"💾 Saved screenshot: {screenshot_path}")
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ Screenshot save timeout for {job_id}")
            except Exception as e:
                logger.warning(f"Failed to save screenshot: {e}")
            
            # XHR info - always try to save if available
            if xhr_info:
                xhr_path = DEBUG_DIR / f"{job_id}_xhr.json"
                try:
                    with open(xhr_path, "w", encoding="utf-8") as f:
                        json.dump(xhr_info, f, indent=2, ensure_ascii=False)
                    saved_artifacts.append("XHR")
                    logger.info(f"💾 Saved XHR info: {xhr_path}")
                except Exception as e:
                    logger.warning(f"Failed to save XHR info: {e}")
            
            # Save error log
            error_log_path = DEBUG_DIR / f"{job_id}_error.txt"
            try:
                error_log_path.write_text(
                    f"Error: {error_msg}\n"
                    f"Job ID: {job_id}\n"
                    f"Timestamp: {time.time()}\n"
                    f"Artifacts saved: {', '.join(saved_artifacts) if saved_artifacts else 'none'}\n",
                    encoding="utf-8"
                )
            except Exception as e:
                logger.warning(f"Failed to save error log: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to save debug artifacts: {e}", exc_info=True)
    
    async def _try_distribution_method(self, url: str) -> Optional[str]:
        """
        Try official Yandex Distribution method.
        
        Returns:
            Partner link if successful, None otherwise
        """
        try:
            from src.utils.partner_link_builder import check_distribution_available, build_partner_link
            
            is_available, clid, vid = check_distribution_available()
            if is_available and clid and vid:
                logger.info("✅ Using official Yandex Distribution method")
                try:
                    partner_link = build_partner_link(url, clid, vid)
                    return partner_link
                except Exception as e:
                    logger.warning(f"⚠️ Distribution method failed: {e}, falling back to browser")
        except Exception as e:
            logger.debug(f"Distribution check failed: {e}")
        
        return None
    
    def _get_storage_state_path_for_reuse(self, url: str, reuse_state_path: Optional[str] = None) -> Optional[str]:
        """
        Get storage state path for reuse.
        
        Returns:
            Path to storage state file or None
        """
        # Убеждаемся, что директория существует
        STORAGE_STATE_DIR.mkdir(exist_ok=True, parents=True)
        
        if reuse_state_path and reuse_state_path.strip():
            state_file = Path(reuse_state_path)
            if state_file.exists():
                return str(state_file)
        
        existing_state = self._get_storage_state_path(url)
        if existing_state:
            return str(existing_state)
        
        return None
    
    def _setup_network_interception(self, page, captured: Dict[str, Any], job_id: Optional[str] = None):
        """
        Setup network request/response interception with structured dump.
        Network interception is enabled BEFORE Share button click.
        
        Args:
            page: Playwright page object
            captured: Dict to store captured data
            job_id: Optional job identifier for network dump file
        """
        # Initialize network dump storage
        if "network_dump" not in captured:
            captured["network_dump"] = []
        
        def on_request(request):
            """Capture XHR requests for reproduction."""
            try:
                url_str = request.url
                method = request.method
                
                if any(pattern in url_str for pattern in NETWORK_API_PATTERNS) and method in ("POST", "GET", "PUT"):
                    headers = request.headers
                    post_data = request.post_data
                    
                    xhr_info = {
                        "method": method,
                        "url": url_str,
                        "headers": dict(headers),
                        "body": post_data,
                        "timestamp": time.time()
                    }
                    
                    captured["xhr_info"] = xhr_info
                    logger.info(f"📡 Captured XHR: {method} {url_str[:100]}...")
            except Exception as e:
                logger.debug(f"Request capture error: {e}")
        
        async def on_response(response):
            """Handle network responses - PRIMARY METHOD with structured dump."""
            try:
                url_str = str(response.url)
                status = response.status
                content_type = response.headers.get('content-type', '')
                
                # Check if response URL contains /cc/
                if "/cc/" in url_str:
                    cc_link = self._extract_cc_link(url_str)
                    if cc_link:
                        captured["link"] = cc_link
                        logger.info(f"🌐 Found /cc/ link in response URL: {cc_link}")
                        
                        # Save to network dump
                        captured["network_dump"].append({
                            "url": url_str,
                            "status": status,
                            "content_type": content_type,
                            "snippet": f"Found CC link: {cc_link}",
                            "timestamp": time.time(),
                            "cc_link_found": True
                        })
                        return
                
                # Check API responses (XHR/Fetch) - IMPROVED: Also check text responses
                is_api_response = any(pattern in url_str for pattern in NETWORK_API_PATTERNS)
                is_json_response = 'application/json' in content_type
                is_text_response = 'text/' in content_type or 'application/' in content_type
                
                # Check ALL market.yandex responses (not just API patterns) for CC links
                is_market_response = 'market.yandex' in url_str.lower() and status == 200                
                if (is_api_response or is_market_response) and status == 200:
                    try:
                        # Try JSON first
                        if is_json_response:
                            data = await response.json()
                            captured["response_data"] = data
                            
                            # Extract snippet (first 500 chars of JSON string)
                            json_str = json.dumps(data, ensure_ascii=False)
                            snippet = json_str[:500] + ("..." if len(json_str) > 500 else "")
                            
                            # Look for shortUrl in common locations
                            cc_link = None
                            if isinstance(data, dict):                                # #endregion
                                
                                # Direct fields
                                # #region agent edit - дополнительные поля для resolveSharingPopupV2
                                short_url = (
                                    data.get('shortUrl') or
                                    data.get('short_url') or
                                    data.get('url') or
                                    data.get('link') or
                                    data.get('data', {}).get('shortUrl') or
                                    data.get('result', {}).get('shortUrl') or
                                    data.get('payload', {}).get('shortUrl') or
                                    data.get('response', {}).get('shortUrl') or
                                    data.get('widgets', {}).get('@marketfront/SpeculationVelocityLink', {}).get('/linkSpeculation', {}).get('shortUrl') or
                                    data.get('widgets', {}).get('@marketfront/SpeculationVelocityLink', {}).get('/linkSpeculation', {}).get('url') or
                                    data.get('collections', {}).get('linkSpeculation', {}).get('shortUrl') or
                                    data.get('collections', {}).get('linkSpeculation', {}).get('url') or
                                    # #region agent edit - обработка структуры results[0].data.result для resolveSharingPopupV2
                                    (data.get('results') and isinstance(data.get('results'), list) and len(data.get('results')) > 0 and 
                                     data.get('results')[0].get('data', {}).get('result', {}).get('shortUrl')) or
                                    (data.get('results') and isinstance(data.get('results'), list) and len(data.get('results')) > 0 and 
                                     data.get('results')[0].get('data', {}).get('result', {}).get('url')) or
                                    (data.get('results') and isinstance(data.get('results'), list) and len(data.get('results')) > 0 and 
                                     data.get('results')[0].get('data', {}).get('result', {}).get('link')) or
                                    # Ищем в sharingOptions
                                    (data.get('results') and isinstance(data.get('results'), list) and len(data.get('results')) > 0 and 
                                     data.get('results')[0].get('data', {}).get('result', {}).get('sharingOptions') and
                                     isinstance(data.get('results')[0].get('data', {}).get('result', {}).get('sharingOptions'), list) and
                                     any(opt.get('url') or opt.get('link') or opt.get('shortUrl') 
                                         for opt in data.get('results')[0].get('data', {}).get('result', {}).get('sharingOptions', [])
                                         if isinstance(opt, dict)) and
                                     next((opt.get('url') or opt.get('link') or opt.get('shortUrl')
                                           for opt in data.get('results')[0].get('data', {}).get('result', {}).get('sharingOptions', [])
                                           if isinstance(opt, dict) and (opt.get('url') or opt.get('link') or opt.get('shortUrl'))), None))
                                    # #endregion
                                )
                                # #endregion                                
                                if short_url:
                                    cc_link = self._extract_cc_link(short_url)
                                    if cc_link:
                                        captured["link"] = cc_link
                                        logger.info(f"🌐 Found shortUrl in JSON: {cc_link}")                                        
                                        # Save to network dump
                                        captured["network_dump"].append({
                                            "url": url_str,
                                            "status": status,
                                            "content_type": content_type,
                                            "snippet": snippet,
                                            "timestamp": time.time(),
                                            "cc_link_found": True,
                                            "cc_link": cc_link,
                                            "found_in": "direct_field"
                                        })
                                        return
                                
                                # Deep recursive search for CC links (увеличена глубина до 25)
                                found_link = self._search_cc_link_recursive(data, max_depth=25)
                                if found_link:
                                    cc_link = found_link
                                    captured["link"] = cc_link
                                    logger.info(f"🌐 Found CC link via recursive search: {cc_link}")                                    
                                    # Save to network dump
                                    captured["network_dump"].append({
                                        "url": url_str,
                                        "status": status,
                                        "content_type": content_type,
                                        "snippet": snippet,
                                        "timestamp": time.time(),
                                        "cc_link_found": True,
                                        "cc_link": cc_link,
                                        "found_in": "recursive_search"
                                    })
                                    return
                            
                            # Save all API responses to dump (even if no CC link found)
                            captured["network_dump"].append({
                                "url": url_str,
                                "status": status,
                                "content_type": content_type,
                                "snippet": snippet,
                                "timestamp": time.time(),
                                "cc_link_found": False,
                                "is_api_response": True
                            })
                        else:
                            # IMPROVED: Also parse text responses (HTML, plain text, etc.)
                            try:
                                text = await response.text()
                                if text and len(text) > 0:
                                    # Search for CC links in text using regex patterns
                                    cc_patterns = [
                                        r'"shortUrl"\s*:\s*"([^"]+)"',  # JSON-like: "shortUrl": "..."
                                        r'"cc"\s*:\s*"([a-zA-Z0-9=,\-_]+)"',  # JSON-like: "cc": "..."
                                        r'market\.yandex\.ru/cc/([a-zA-Z0-9=,\-_]+)',  # URL pattern
                                        r'/cc/([a-zA-Z0-9=,\-_]+)',  # Short pattern
                                        r'cc["\']?\s*[:=]\s*["\']?([a-zA-Z0-9=,\-_]+)',  # Generic cc:value
                                    ]
                                    
                                    for pattern in cc_patterns:
                                        matches = re.findall(pattern, text, re.IGNORECASE)
                                        if matches:
                                            for match in matches:
                                                # Clean up match (remove trailing comma)
                                                cc_code = match.rstrip(',').strip()
                                                if len(cc_code) > 10:  # Basic validation
                                                    cc_link = f"https://market.yandex.ru/cc/{cc_code}"
                                                    if self._extract_cc_link(cc_link):
                                                        captured["link"] = cc_link
                                                        logger.info(f"🌐 Found CC link in text response via regex: {cc_link}")                                                        
                                                        # Save to network dump
                                                        snippet = text[:500] + ("..." if len(text) > 500 else "")
                                                        captured["network_dump"].append({
                                                            "url": url_str,
                                                            "status": status,
                                                            "content_type": content_type,
                                                            "snippet": snippet,
                                                            "timestamp": time.time(),
                                                            "cc_link_found": True,
                                                            "cc_link": cc_link,
                                                            "found_in": f"text_regex_{pattern[:20]}"
                                                        })
                                                        return
                                    
                                    # Save text response to dump (even if no CC found)
                                    snippet = text[:500] + ("..." if len(text) > 500 else "")
                                    captured["network_dump"].append({
                                        "url": url_str,
                                        "status": status,
                                        "content_type": content_type,
                                        "snippet": snippet,
                                        "timestamp": time.time(),
                                        "cc_link_found": False,
                                        "is_text_response": True,
                                        "text_length": len(text)
                                    })
                            except Exception as text_error:
                                logger.debug(f"Error reading text response: {text_error}")
                    except Exception as e:
                        logger.debug(f"Error parsing response: {e}")
                        # Save error to dump
                        captured["network_dump"].append({
                            "url": url_str,
                            "status": status,
                            "content_type": content_type,
                            "snippet": f"Error parsing response: {str(e)[:200]}",
                            "timestamp": time.time(),
                            "cc_link_found": False,
                            "parse_error": str(e)
                        })
                
                # Check redirects
                if 300 <= status < 400:
                    location = response.headers.get('location', '')
                    if location:
                        cc_link = self._extract_cc_link(location)
                        if cc_link:
                            captured["link"] = cc_link
                            logger.info(f"🌐 Found /cc/ link in redirect: {cc_link}")
                            
                            # Save to network dump
                            captured["network_dump"].append({
                                "url": url_str,
                                "status": status,
                                "content_type": content_type,
                                "snippet": f"Redirect to: {location}",
                                "timestamp": time.time(),
                                "cc_link_found": True,
                                "cc_link": cc_link,
                                "found_in": "redirect_location"
                            })
                            
            except Exception as e:
                logger.debug(f"Response handler error: {e}")
        
        # Enable interception BEFORE any button clicks
        page.on("request", on_request)
        page.on("response", on_response)
        
        logger.info("✅ Network interception enabled (before Share button click)")
    
    def _init_captcha_solver(self):
        """Инициализировать решатель CAPTCHA, если доступен API ключ."""
        try:
            from src.utils.captcha_solver import CaptchaSolver
            import src.config as config
            if hasattr(config, 'CAPTCHA_API_KEY') and config.CAPTCHA_API_KEY:
                service = getattr(config, 'CAPTCHA_SERVICE', 'rucaptcha')
                self._captcha_solver = CaptchaSolver(
                    api_key=config.CAPTCHA_API_KEY,
                    service=service,
                    timeout=120
                )
                logger.info(f"✅ CAPTCHA solver initialized: {service}")
                return True
            else:
                logger.debug("CAPTCHA API key not found, captcha solver disabled")
                self._captcha_solver = None
                return False
        except Exception as e:
            logger.debug(f"Failed to initialize captcha solver: {e}")
            self._captcha_solver = None
            return False
    
    async def _check_and_handle_captcha(self, page, job_id: Optional[str] = None) -> bool:
        """
        Check for CAPTCHA on the page and handle it.
        
        Args:
            page: Playwright page object
            job_id: Optional job identifier for debug artifacts
            
        Returns:
            True if CAPTCHA detected, False otherwise
        """
        try:
            # Check URL for captcha
            current_url = page.url
            if 'captcha' in current_url.lower() or 'yandex.ru/showcaptcha' in current_url.lower() or 'showcaptcha' in current_url.lower():
                logger.error("🚫 CAPTCHA detected in URL!")
                if self.debug and job_id:
                    await page.screenshot(path=str(DEBUG_DIR / f"{job_id}_captcha.jpg"), full_page=True)
                
                # Пытаемся решить автоматически через rucaptcha
                if self._captcha_solver:
                    logger.info("🤖 Attempting to solve CAPTCHA automatically via rucaptcha...")
                    try:
                        from src.utils.captcha_solver import detect_captcha_on_page, solve_captcha_in_browser
                        captcha_info = await detect_captcha_on_page(page)
                        if captcha_info:
                            solved = await solve_captcha_in_browser(page, captcha_info, self._captcha_solver)
                            if solved:
                                logger.info("✅ CAPTCHA solved automatically!")
                                await self._save_storage_state(page.context, current_url, only_if_success=True)
                                return False  # CAPTCHA решена
                            else:
                                logger.warning("⚠️ Automatic CAPTCHA solving failed, falling back to manual")
                    except Exception as e:
                        logger.warning(f"⚠️ Error during automatic CAPTCHA solving: {e}, falling back to manual")
                
                # Fallback: ждем ручного решения (если автоматическое не сработало или решатель недоступен)
                if not self.headless:
                    logger.warning("⏳ Ожидаю решения CAPTCHA вручную (браузер видимый)...")
                    logger.warning("   Пожалуйста, решите CAPTCHA в открывшемся браузере")
                    logger.warning("   Бот будет ждать до 5 минут...")
                    # Ждем до 5 минут, пока CAPTCHA не будет решена
                    # Проверяем каждые 2 секунды, изменился ли URL
                    for attempt in range(150):  # 150 * 2 секунды = 5 минут
                        await asyncio.sleep(2)
                        new_url = page.url
                        if 'captcha' not in new_url.lower() and 'showcaptcha' not in new_url.lower():
                            logger.info("✅ CAPTCHA решена, продолжаю...")
                            # Сохраняем состояние после решения CAPTCHA
                            await self._save_storage_state(page.context, current_url, only_if_success=True)
                            return False
                        if attempt % 15 == 0 and attempt > 0:  # Каждые 30 секунд
                            logger.info(f"⏳ Ожидаю решения CAPTCHA... (попытка {attempt}/150, прошло {attempt * 2} секунд)")
                    logger.error("⏱️ Timeout ожидания решения CAPTCHA (5 минут)")
                    return True
                return True
            
            # Check for CAPTCHA iframe
            try:
                captcha_iframe_count = await page.locator('iframe[src*="captcha"], iframe[src*="showcaptcha"]').count()
                if captcha_iframe_count > 0:
                    logger.error("🚫 CAPTCHA iframe detected!")
                    if self.debug and job_id:
                        await page.screenshot(path=str(DEBUG_DIR / f"{job_id}_captcha.jpg"), full_page=True)
                    if not self.headless:
                        logger.warning("⏳ Ожидаю решения CAPTCHA вручную...")
                        logger.warning("   Пожалуйста, решите CAPTCHA в открывшемся браузере")
                        logger.warning("   Бот будет ждать до 5 минут...")
                        # Ждем до 5 минут
                        for attempt in range(150):  # 150 * 2 секунды = 5 минут
                            await asyncio.sleep(2)
                            captcha_iframe_count = await page.locator('iframe[src*="captcha"], iframe[src*="showcaptcha"]').count()
                            if captcha_iframe_count == 0:
                                logger.info("✅ CAPTCHA решена")
                                await self._save_storage_state(page.context, page.url, only_if_success=True)
                                return False
                            if attempt % 15 == 0 and attempt > 0:  # Каждые 30 секунд
                                logger.info(f"⏳ Ожидаю решения CAPTCHA... (попытка {attempt}/150, прошло {attempt * 2} секунд)")
                        logger.error("⏱️ Timeout ожидания решения CAPTCHA (5 минут)")
                    return True
            except Exception as e:
                logger.debug(f"Error checking CAPTCHA iframe: {e}")
                pass
            
            # Check for CAPTCHA text/elements (Я не робот, Вы не робот, и т.д.)
            try:
                page_text = await page.text_content('body')
                if page_text:
                    captcha_indicators = ['я не робот', 'вы не робот', 'i am not a robot', 'подтвердите, что запросы отправляли вы', 'smartcaptcha', 'нажмите в таком порядке']
                    for indicator in captcha_indicators:
                        if indicator in page_text.lower():
                            logger.error(f"🚫 CAPTCHA text detected: '{indicator}'")                            if self.debug and job_id:
                                await page.screenshot(path=str(DEBUG_DIR / f"{job_id}_captcha_text.jpg"), full_page=True)
                            if not self.headless:
                                logger.warning("⏳ Ожидаю решения CAPTCHA вручную...")
                                logger.warning("   Пожалуйста, решите CAPTCHA в открывшемся браузере")
                                logger.warning("   Бот будет ждать до 5 минут...")
                                # Ждем до 5 минут, проверяя каждые 2 секунды
                                for attempt in range(150):  # 150 * 2 секунды = 5 минут
                                    await asyncio.sleep(2)
                                    new_text = await page.text_content('body')
                                    if new_text:
                                        has_captcha = any(ind in new_text.lower() for ind in captcha_indicators)                                        if not has_captcha:
                                            logger.info("✅ CAPTCHA решена")
                                            await self._save_storage_state(page.context, page.url, only_if_success=True)                                            return False
                                    if attempt % 15 == 0 and attempt > 0:  # Каждые 30 секунд
                                        logger.info(f"⏳ Ожидаю решения CAPTCHA... (попытка {attempt}/150, прошло {attempt * 2} секунд)")
                                logger.error("⏱️ Timeout ожидания решения CAPTCHA (5 минут)")
                            return True
            except Exception as e:
                logger.debug(f"Error checking CAPTCHA text: {e}")
                pass
            
            return False
        except Exception as e:
            logger.debug(f"CAPTCHA check error: {e}")
            return False
    
    async def _check_login_required(self, page, job_id: Optional[str] = None) -> bool:
        """
        Проверяет, требуется ли вход в аккаунт.
        
        Args:
            page: Playwright page object
            job_id: Optional job identifier for debug artifacts
            
        Returns:
            True if login required, False otherwise
        """
        try:
            # Проверяем наличие текста "Войдите" или "Войти"
            page_text = await page.text_content('body')
            if page_text:
                login_indicators = [
                    'войдите, и станет дешевле',
                    'в аккаунте больше скидок',
                    'войти',
                    'вход',
                    'авторизация'
                ]
                for indicator in login_indicators:
                    if indicator in page_text.lower():
                        logger.warning(f"⚠️ Обнаружен индикатор входа: '{indicator}'")                        if self.debug and job_id:
                            await page.screenshot(path=str(DEBUG_DIR / f"{job_id}_login_required.jpg"), full_page=True)
                        return True
            
            # Проверяем наличие кнопки "Войти"
            login_button = page.locator('button:has-text("Войти"), a:has-text("Войти"), button:has-text("Вход"), a:has-text("Вход")')
            if await login_button.count() > 0:
                logger.warning("⚠️ Обнаружена кнопка входа")                return True
            
            return False
        except Exception as e:
            logger.warning(f"Error checking login required: {e}")
            return False
    
    def _search_cc_link_recursive(self, data: Any, max_depth: int = 25, current_depth: int = 0, visited: Optional[set] = None) -> Optional[str]:
        """
        МАКСИМАЛЬНО УЛУЧШЕННЫЙ рекурсивный поиск CC ссылок в вложенных структурах данных.
        Использует приоритетный поиск по ключевым полям и предотвращает бесконечные циклы.
        
        Args:
            data: Data to search (dict, list, or str)
            max_depth: Maximum recursion depth (увеличено до 25)
            current_depth: Current recursion depth
            visited: Set of visited objects to prevent cycles
            
        Returns:
            CC link if found, None otherwise
        """
        if current_depth >= max_depth:
            return None
        
        # Предотвращение бесконечных циклов
        if visited is None:
            visited = set()
        
        # Проверяем, не посещали ли мы уже этот объект
        obj_id = id(data)
        if obj_id in visited:
            return None
        visited.add(obj_id)
        
        try:
            if isinstance(data, dict):
                # #region agent edit - ПРИОРИТЕТНЫЙ ПОИСК: сначала проверяем ключевые поля
                # Приоритетные ключи (в порядке важности)
                priority_keys = [
                    'shortUrl', 'short_url', 'url', 'link', 'href',
                    'cc', 'ccLink', 'cc_link', 'refLink', 'ref_link',
                    'shareUrl', 'share_url', 'sharingUrl', 'sharing_url',
                    'result', 'data', 'payload', 'response'
                ]
                
                # Сначала проверяем приоритетные ключи
                for key in priority_keys:
                    if key in data:
                        value = data[key]
                        if isinstance(value, str):
                            cc_link = self._extract_cc_link(value)
                            if cc_link:
                                return cc_link
                        elif isinstance(value, (dict, list)):
                            result = self._search_cc_link_recursive(value, max_depth, current_depth + 1, visited.copy())
                            if result:
                                return result
                
                # Проверяем ключи, содержащие подсказки
                for key, value in data.items():
                    if isinstance(key, str):
                        key_lower = key.lower()
                        # Пропускаем уже проверенные приоритетные ключи
                        if any(prio in key_lower for prio in ['url', 'link', 'short', 'cc', 'ref', 'share']):
                            if isinstance(value, str):
                                cc_link = self._extract_cc_link(value)
                                if cc_link:
                                    return cc_link
                            elif isinstance(value, (dict, list)):
                                result = self._search_cc_link_recursive(value, max_depth, current_depth + 1, visited.copy())
                                if result:
                                    return result
                
                # Рекурсивно ищем во всех остальных значениях
                for key, value in data.items():
                    if isinstance(value, (dict, list, str)):
                        result = self._search_cc_link_recursive(value, max_depth, current_depth + 1, visited.copy())
                        if result:
                            return result
                # #endregion
                
            elif isinstance(data, list):
                # #region agent edit - УЛУЧШЕННЫЙ ПОИСК В СПИСКАХ: проверяем первые элементы и sharingOptions
                # Сначала проверяем первые несколько элементов (обычно там важные данные)
                for i, item in enumerate(data[:10]):  # Проверяем первые 10 элементов
                    if isinstance(item, (dict, list, str)):
                        result = self._search_cc_link_recursive(item, max_depth, current_depth + 1, visited.copy())
                        if result:
                            return result
                
                # Если это sharingOptions, проверяем все элементы
                if current_depth < 3:  # Только на верхних уровнях
                    for item in data:
                        if isinstance(item, dict) and isinstance(item.get('action'), str):
                            # Проверяем поля url, link, shortUrl в элементах sharingOptions
                            for field in ['url', 'link', 'shortUrl']:
                                if field in item and isinstance(item[field], str):
                                    cc_link = self._extract_cc_link(item[field])
                                    if cc_link:
                                        return cc_link
                
                # Проверяем остальные элементы
                for item in data[10:]:
                    if isinstance(item, (dict, list, str)):
                        result = self._search_cc_link_recursive(item, max_depth, current_depth + 1, visited.copy())
                        if result:
                            return result
                # #endregion
                
            elif isinstance(data, str):
                # Проверяем, содержит ли строка CC ссылку
                cc_link = self._extract_cc_link(data)
                if cc_link:
                    return cc_link
        finally:
            # Удаляем объект из visited при выходе (для экономии памяти)
            visited.discard(obj_id)
        
        return None
    
    async def _save_network_dump(self, captured: Dict[str, Any], job_id: Optional[str] = None):
        """
        Save structured network dump to JSON file.
        
        Args:
            captured: Dict containing network_dump array
            job_id: Optional job identifier for filename
        """
        if not self.debug:
            return
        
        network_dump = captured.get("network_dump", [])
        if not network_dump:
            logger.debug("No network dump data to save")
            return
        
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"debug_ref_link_network_{timestamp}"
            if job_id:
                filename += f"_{job_id}"
            filename += ".json"
            
            dump_path = DEBUG_DIR / filename
            
            # Prepare structured dump
            structured_dump = {
                "metadata": {
                    "timestamp": timestamp,
                    "job_id": job_id,
                    "total_responses": len(network_dump),
                    "cc_links_found": sum(1 for r in network_dump if r.get("cc_link_found", False))
                },
                "responses": network_dump
            }
            
            # Save to file
            with open(dump_path, 'w', encoding='utf-8') as f:
                json.dump(structured_dump, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Saved network dump: {dump_path} ({len(network_dump)} responses)")
            
        except Exception as e:
            logger.warning(f"Failed to save network dump: {e}")
    
    async def _apply_stealth_and_anti_detection(self, page, context):
        """
        Apply stealth plugin and anti-detection measures reliably.
        Ensures UA rotation and stealth are always applied.
        
        Args:
            page: Playwright page object
            context: Browser context (for verification)
        """
        # Verify UA was set correctly
        try:
            context_ua = await context.evaluate("() => navigator.userAgent")
            logger.debug(f"🔍 Context UA: {context_ua[:50]}...")
        except Exception as e:
            logger.debug(f"Could not verify UA: {e}")
        
        # Apply stealth plugin (if available)
        if self.stealth_available:
            try:
                await asyncio.wait_for(
                    self.stealth_async(page),
                    timeout=5.0
                )
                logger.info("✅ Stealth plugin applied successfully")
                
                # Verify stealth was applied
                try:
                    webdriver = await page.evaluate("() => navigator.webdriver")
                    if webdriver is None or webdriver is False:
                        logger.debug("✅ Stealth verification: webdriver property hidden")
                    else:
                        logger.warning("⚠️ Stealth verification: webdriver property still visible")
                except Exception:
                    pass  # Verification is optional
                    
            except asyncio.TimeoutError:
                logger.warning("⚠️ Stealth plugin application timed out, using fallback")
                await self._apply_fallback_anti_detection(page)
            except Exception as e:
                logger.warning(f"⚠️ Failed to apply stealth plugin: {e}, using fallback")
                await self._apply_fallback_anti_detection(page)
        else:
            # Fallback: basic anti-bot measures
            await self._apply_fallback_anti_detection(page)
    
    async def _apply_fallback_anti_detection(self, page):
        """
        Apply comprehensive fallback anti-detection measures.
        Covers navigator properties, plugins, permissions, and other browser fingerprints.
        """
        try:
            await page.add_init_script("""
                // Hide webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Fake plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => {
                        return [
                            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                            { name: 'Native Client', filename: 'internal-nacl-plugin' }
                        ];
                    }
                });
                
                // Fake chrome object
                window.chrome = { 
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };
                
                // Set languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['ru-RU', 'ru', 'en-US', 'en']
                });
                
                // Override permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Override plugins length
                Object.defineProperty(navigator, 'mimeTypes', {
                    get: () => {
                        return {
                            length: 0,
                            item: () => null,
                            namedItem: () => null
                        };
                    }
                });
                
                // Override platform
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'Win32'
                });
                
                // Override hardwareConcurrency (make it realistic)
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 8
                });
                
                // Override deviceMemory
                Object.defineProperty(navigator, 'deviceMemory', {
                    get: () => 8
                });
                
                // Remove automation indicators
                delete navigator.__proto__.webdriver;
            """)
            logger.info("✅ Comprehensive fallback anti-detection measures applied")
        except Exception as e:
            logger.warning(f"⚠️ Failed to apply fallback anti-detection: {e}")
    
    
    async def _human_like_mouse_move(self, page, target_element, start_x: Optional[float] = None, start_y: Optional[float] = None):
        """
        Simulate human-like mouse movement to target element.
        Moves mouse in a curved path with random delays.
        
        Args:
            page: Playwright page object
            target_element: Target element to move to
            start_x: Optional starting X coordinate
            start_y: Optional starting Y coordinate
        """
        try:
            # Get element bounding box
            box = await target_element.bounding_box()
            if not box:
                return
            
            target_x = box['x'] + box['width'] / 2
            target_y = box['y'] + box['height'] / 2
            
            # Get current mouse position or use start position
            if start_x is None or start_y is None:
                try:
                    current_pos = await page.evaluate("() => ({ x: window.mouseX || 0, y: window.mouseY || 0 })")
                    start_x = current_pos.get('x', 0)
                    start_y = current_pos.get('y', 0)
                except Exception:
                    start_x = 0
                    start_y = 0
            
            # Calculate distance
            dx = target_x - start_x
            dy = target_y - start_y
            distance = (dx ** 2 + dy ** 2) ** 0.5
            
            # Move in steps (human-like curved path)
            steps = max(3, int(distance / 50))  # At least 3 steps, more for longer distances
            
            for i in range(steps + 1):
                # Bezier curve interpolation for natural movement
                t = i / steps
                # Add slight randomness to path
                curve_offset = random.uniform(-5, 5) if i > 0 and i < steps else 0
                
                x = start_x + dx * t + curve_offset
                y = start_y + dy * t + curve_offset
                
                await page.mouse.move(x, y)
                
                # Random delay between movements (human-like)
                if i < steps:
                    delay = random.uniform(MOUSE_MOVE_DELAY_MIN, MOUSE_MOVE_DELAY_MAX)
                    await asyncio.sleep(delay)
            
        except Exception as e:
            logger.debug(f"Human-like mouse move failed: {e}")
            # Fallback: just move directly
            try:
                await target_element.hover()
            except Exception:
                pass
    
    async def _human_like_click(self, page, element):
        """
        Simulate human-like click with mouse down/up sequence.
        
        Args:
            page: Playwright page object
            element: Element to click
        """
        try:
            # Get element center
            box = await element.bounding_box()
            if not box:
                # Fallback to regular click
                await element.click()
                return
            
            x = box['x'] + box['width'] / 2
            y = box['y'] + box['height'] / 2
            
            # Move to element (if not already there)
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(CLICK_DELAY_MIN, CLICK_DELAY_MAX))
            
            # Mouse down
            await page.mouse.down()
            await asyncio.sleep(random.uniform(0.05, 0.15))  # Brief hold
            
            # Mouse up
            await page.mouse.up()
            await asyncio.sleep(random.uniform(0.05, 0.1))  # Brief pause after click
            
        except Exception as e:
            logger.debug(f"Human-like click failed: {e}, using fallback")
            # Fallback to regular click
            try:
                await element.click()
            except Exception:
                pass
    
    async def _try_button_click(
        self,
        page,
        captured: Dict[str, Any],
        cancellation_token: Optional[asyncio.CancelledError] = None
    ) -> Optional[str]:
        """
        Try clicking "Share" button with retries using human-like actions.
        RELIABLE BROWSER FALLBACK with stealth, cookies, and network interception.
        
        Args:
            page: Playwright page object
            captured: Dict to store captured data (network interception active)
            cancellation_token: Optional cancellation token
            
        Returns:
            Partner link if successful, None otherwise
        """
        logger.info("🔄 STEP 5: Trying button click fallback (with stealth + human-like actions)...")
        
        # Check cancellation
        if cancellation_token and cancellation_token.is_set():
            raise asyncio.CancelledError("Button click cancelled")
        
        # Find share button with multiple selectors
        share_button = None
        used_selector = None        for selector in SHARE_BUTTON_SELECTORS:
            try:
                share_button = await asyncio.wait_for(
                    page.query_selector(selector),
                    timeout=3.0
                )
                if share_button:
                    used_selector = selector
                    logger.info(f"✅ Found share button: {selector}")                    break
            except asyncio.TimeoutError:                continue
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")                continue
        
        if not share_button:            raise ButtonNotFoundError(
                f"Share button not found on page (tried {len(SHARE_BUTTON_SELECTORS)} selectors)",
                xhr_info=captured.get("xhr_info")
            )
        
        # Try clicking with retries (human-like interaction)
        for attempt in range(self.max_retries):
            if captured.get("link"):
                logger.info(f"✅ Link already captured, skipping button click")
                break
            
            # Check cancellation before each attempt
            if cancellation_token and cancellation_token.is_set():
                raise asyncio.CancelledError("Button click cancelled")
            
            try:
                logger.debug(f"🔄 Button click attempt {attempt + 1}/{self.max_retries}")
                
                # STEP 1: Scroll to share area (human-like)
                try:
                    await asyncio.wait_for(
                        share_button.scroll_into_view_if_needed(),
                        timeout=5.0
                    )
                    # Small delay after scroll (human-like)
                    await asyncio.sleep(random.uniform(0.2, 0.4))
                    logger.debug("✅ Scrolled to share button")
                except asyncio.TimeoutError:
                    logger.debug("⚠️ Scroll timeout, continuing")
                except Exception as e:
                    logger.debug(f"⚠️ Scroll failed: {e}, continuing")
                
                # STEP 2: Human-like mouse movement to button
                try:
                    await self._human_like_mouse_move(page, share_button)
                    logger.debug("✅ Mouse moved to button (human-like)")
                except Exception as e:
                    logger.debug(f"⚠️ Human-like mouse move failed: {e}, using hover")
                    try:
                        await share_button.hover()
                    except Exception:
                        pass
                
                # STEP 3: Hover with delay (human-like pause)
                try:
                    await asyncio.wait_for(
                        share_button.hover(),
                        timeout=3.0
                    )
                    # Human-like hover delay (varies by attempt)
                    hover_delay = random.uniform(HOVER_DELAY_MIN, HOVER_DELAY_MAX)
                    if attempt == 0:
                        hover_delay *= 1.5  # Longer delay on first attempt
                    await asyncio.sleep(hover_delay)
                    logger.debug(f"✅ Hovered over button (delay: {hover_delay:.2f}s)")
                except asyncio.TimeoutError:
                    logger.debug("⚠️ Hover timeout, continuing")
                except Exception as e:
                    logger.debug(f"⚠️ Hover failed: {e}, continuing")
                
                # STEP 4: Click with network interception (PRIMARY - network interception from Task 1.1)
                # Network interception is already active from _setup_network_interception
                # #region agent edit - МАКСИМАЛЬНО УЛУЧШЕННЫЙ СПОСОБ: перехватываем ВСЕ XHR запросы после клика
                xhr_captured_links = {"links": []}
                async def capture_all_xhr_after_share(response):
                    try:
                        url_str = response.url
                        # #region agent edit - улучшенная обработка ответа resolveSharingPopupV2
                        is_sharing_request = 'resolveSharingPopupV2' in url_str or 'sharing' in url_str.lower()
                        if response.status == 200:
                            try:
                                data = await response.json()                                
                                # Используем ту же логику извлечения, что и в основном обработчике
                                cc_link = None
                                if isinstance(data, dict):
                                    # Прямые поля (как в основном обработчике)
                                    short_url = (
                                        data.get('shortUrl') or
                                        data.get('short_url') or
                                        data.get('url') or
                                        data.get('link') or
                                        data.get('data', {}).get('shortUrl') or
                                        data.get('result', {}).get('shortUrl') or
                                        data.get('payload', {}).get('shortUrl') or
                                        data.get('response', {}).get('shortUrl') or
                                        data.get('widgets', {}).get('@marketfront/SpeculationVelocityLink', {}).get('/linkSpeculation', {}).get('shortUrl') or
                                        data.get('widgets', {}).get('@marketfront/SpeculationVelocityLink', {}).get('/linkSpeculation', {}).get('url') or
                                        data.get('collections', {}).get('linkSpeculation', {}).get('shortUrl') or
                                        data.get('collections', {}).get('linkSpeculation', {}).get('url') or
                                        # Обработка структуры results[0].data.result для resolveSharingPopupV2
                                        (data.get('results') and isinstance(data.get('results'), list) and len(data.get('results')) > 0 and 
                                         data.get('results')[0].get('data', {}).get('result', {}).get('shortUrl')) or
                                        (data.get('results') and isinstance(data.get('results'), list) and len(data.get('results')) > 0 and 
                                         data.get('results')[0].get('data', {}).get('result', {}).get('url')) or
                                        (data.get('results') and isinstance(data.get('results'), list) and len(data.get('results')) > 0 and 
                                         data.get('results')[0].get('data', {}).get('result', {}).get('link')) or
                                        # Ищем в sharingOptions
                                        (data.get('results') and isinstance(data.get('results'), list) and len(data.get('results')) > 0 and 
                                         data.get('results')[0].get('data', {}).get('result', {}).get('sharingOptions') and
                                         isinstance(data.get('results')[0].get('data', {}).get('result', {}).get('sharingOptions'), list) and
                                         any(opt.get('url') or opt.get('link') or opt.get('shortUrl') 
                                             for opt in data.get('results')[0].get('data', {}).get('result', {}).get('sharingOptions', [])
                                             if isinstance(opt, dict)) and
                                         next((opt.get('url') or opt.get('link') or opt.get('shortUrl')
                                               for opt in data.get('results')[0].get('data', {}).get('result', {}).get('sharingOptions', [])
                                               if isinstance(opt, dict) and (opt.get('url') or opt.get('link') or opt.get('shortUrl'))), None))
                                    )
                                    
                                    if short_url:
                                        cc_link = self._extract_cc_link(short_url)
                                        if cc_link:
                                            if cc_link not in xhr_captured_links["links"]:
                                                xhr_captured_links["links"].append(cc_link)
                                                captured["link"] = cc_link
                                                logger.info(f"✅ Found link via XHR after share click (direct field): {cc_link}")                                                return
                                
                                # Если не нашли в прямых полях, ищем рекурсивно
                                if not cc_link:
                                    found_link = self._search_cc_link_recursive(data, max_depth=25)
                                    if found_link:
                                        cc_link = self._extract_cc_link(found_link)
                                        if cc_link and cc_link not in xhr_captured_links["links"]:
                                            xhr_captured_links["links"].append(cc_link)
                                            captured["link"] = cc_link
                                            logger.info(f"✅ Found link via XHR after share click (recursive): {cc_link}")                                            return
                            except Exception as e:                                try:
                                    text = await response.text()
                                    matches = re.findall(r'market\.yandex\.ru/cc/([A-Za-z0-9_-]+)', text, re.IGNORECASE)
                                    if matches:
                                        for match in matches:
                                            if len(match) > 5 and not match.startswith('_0x'):
                                                cc_link = f"https://market.yandex.ru/cc/{match}"
                                                if self._extract_cc_link(cc_link) and cc_link not in xhr_captured_links["links"]:
                                                    xhr_captured_links["links"].append(cc_link)
                                                    captured["link"] = cc_link
                                                    logger.info(f"✅ Found link via XHR text after share click: {cc_link}")                                                    break
                                except:
                                    pass
                        # #endregion
                    except Exception as e:                        pass
                
                # Устанавливаем дополнительный перехватчик для всех ответов после клика на "Поделиться"
                page.on("response", capture_all_xhr_after_share)
                # #endregion
                
                try:
                    # Set up response expectation BEFORE clicking
                    response_promise = page.expect_response(
                        lambda r: (
                            any(pattern in r.url for pattern in NETWORK_API_PATTERNS) or
                            "/cc/" in r.url or
                            "resolve" in r.url.lower() or
                            "share" in r.url.lower()
                        ) and r.status == 200,
                        timeout=NETWORK_RESPONSE_TIMEOUT / 1000  # Convert to seconds
                    )
                    
                    # Human-like click (mouse down/up sequence)                    await self._human_like_click(page, share_button)
                    logger.debug("✅ Clicked button (human-like)")                    
                    # Wait for network response
                    try:
                        # #region agent edit - исправляем обработку таймаута
                        # Используем asyncio.wait_for с правильным таймаутом и обработкой ошибок
                        response = await asyncio.wait_for(
                            response_promise,
                            timeout=NETWORK_RESPONSE_TIMEOUT / 1000 + 5.0  # Увеличиваем таймаут до 15 секунд
                        )
                        # #endregion
                        
                        # Parse response
                        try:
                            data = await asyncio.wait_for(
                                response.json(),
                                timeout=5.0  # Увеличиваем таймаут для парсинга JSON
                            )
                            
                            # Extract shortUrl (network interception may have already captured it)
                            short_url = (
                                data.get('shortUrl') or
                                data.get('short_url') or
                                data.get('url') or
                                data.get('link') or
                                data.get('data', {}).get('shortUrl') or
                                data.get('result', {}).get('shortUrl')
                            )
                            
                            if short_url:
                                cc_link = self._extract_cc_link(short_url)
                                if cc_link:
                                    captured["link"] = cc_link
                                    logger.info(f"✅ Found link via click response: {cc_link}")                                    break
                                else:                        except asyncio.TimeoutError:
                            logger.debug("⚠️ Response parsing timeout")
                        except Exception as e:
                            logger.debug(f"⚠️ Response parsing failed: {e}")
                            
                    except asyncio.TimeoutError:
                        logger.debug(f"⚠️ Network response timeout on attempt {attempt + 1}")
                    except Exception as e:
                        logger.debug(f"⚠️ Network response error: {e}")
                        
                except asyncio.TimeoutError:
                    logger.debug(f"⚠️ Click timeout on attempt {attempt + 1}")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.debug(f"⚠️ Click failed on attempt {attempt + 1}: {e}")
                
                # STEP 5: Check if network interception captured link during click
                if captured.get("link"):
                    logger.info(f"✅ Link captured by network interception: {captured['link']}")                    break
                else:                
                # STEP 6: ROBUST FALLBACK - Try clipboard and DOM search
                # Wait for modal to appear (with increased timeout: 45s)
                # #region agent edit - добавляем проверку модального окна через JavaScript
                modal_found = False
                try:
                    # Сначала проверяем через JavaScript, есть ли модальное окно на странице
                    modal_check_js = """
                    () => {
                        const selectors = %s;
                        for (const selector of selectors) {
                            const elements = document.querySelectorAll(selector);
                            for (const el of elements) {
                                const style = window.getComputedStyle(el);
                                if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                                    return {found: true, selector: selector, text: el.textContent?.substring(0, 100)};
                                }
                            }
                        }
                        return {found: false};
                    }
                    """ % str(SHARE_MODAL_SELECTORS if SHARE_MODAL_SELECTORS else ['[role="dialog"]', '[data-testid*="modal"]', '[class*="Modal"]'])
                    
                    # Проверяем модальное окно каждые 2 секунды в течение 45 секунд
                    for check_attempt in range(23):  # 23 * 2 = 46 секунд
                        # Проверяем, не найдена ли уже ссылка
                        if captured.get("link"):
                            logger.info(f"✅ Link already found, stopping modal check: {captured['link']}")
                            modal_found = True
                            break
                        await asyncio.sleep(2.0)
                        modal_check_result = await page.evaluate(modal_check_js)                        if modal_check_result.get("found"):
                            logger.info(f"✅ Share modal found via JavaScript: {modal_check_result.get('selector')}")
                            modal_found = True
                            # #region agent edit - сразу после обнаружения модального окна ищем ссылку в нем
                            # Ищем ссылку в модальном окне через JavaScript
                            modal_link_js = """
                            () => {
                                // #region agent edit - МАКСИМАЛЬНО УЛУЧШЕННЫЙ ПОИСК: ищем модальное окно всеми возможными способами
                                // Ищем в модальном окне (dialog) - пробуем разные селекторы
                                let modal = document.querySelector('[role="dialog"]');
                                if (!modal) {
                                    modal = document.querySelector('[class*="modal"]');
                                }
                                if (!modal) {
                                    modal = document.querySelector('[class*="Modal"]');
                                }
                                if (!modal) {
                                    modal = document.querySelector('[data-testid*="modal"]');
                                }
                                // Ищем через aria-label
                                if (!modal) {
                                    const modals = document.querySelectorAll('[aria-label*="Поделиться"], [aria-label*="Share"], [aria-label*="поделиться"]');
                                    for (const m of modals) {
                                        const style = window.getComputedStyle(m);
                                        if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                                            modal = m;
                                            break;
                                        }
                                    }
                                }
                                // Ищем через data-атрибуты
                                if (!modal) {
                                    const modals = document.querySelectorAll('[data-modal], [data-dialog], [data-popup]');
                                    for (const m of modals) {
                                        const style = window.getComputedStyle(m);
                                        if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                                            modal = m;
                                            break;
                                        }
                                    }
                                }
                                // Ищем через текст "Поделиться"
                                if (!modal) {
                                    const shareTexts = Array.from(document.querySelectorAll('*')).filter(el => {
                                        const text = el.textContent || el.innerText || '';
                                        return text.includes('Поделиться') || text.includes('Share') || text.includes('поделиться');
                                    });
                                    for (const el of shareTexts) {
                                        let parent = el;
                                        for (let i = 0; i < 5; i++) {
                                            parent = parent.parentElement;
                                            if (!parent) break;
                                            const style = window.getComputedStyle(parent);
                                            if (style.position === 'fixed' || style.position === 'absolute') {
                                                if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                                                    modal = parent;
                                                    break;
                                                }
                                            }
                                        }
                                        if (modal) break;
                                    }
                                }
                                if (!modal) return null;
                                // #endregion
                                
                                // #region agent edit - расширенный поиск ссылки в модальном окне
                                // #region agent edit - ВАЛИДАЦИЯ: список недопустимых кодов
                                const invalidCodes = ['https', 'http', 'www', 'market', 'yandex', 'ru', 'special', 'originals', 'card', 'product', 'catalog', 'search', 'shop', 'seller', 'offer', 'price', 'review', 'rating', 'image', 'photo', 'video', 'javascript', 'void', 'null', 'undefined', 'partner', 'passport', 'auth', 'login', 'register', 'account', 'profile', 'settings', 'help', 'support', 'about', 'contact', 'terms', 'privacy', 'cookie', 'policy', 'legal', 'faq', 'blog', 'news', 'press', 'careers'];
                                // #endregion
                                
                                // 1. Ищем ссылку в input полях (включая скрытые) с валидацией
                                const inputs = modal.querySelectorAll('input, textarea');
                                for (const input of inputs) {
                                    const value = input.value || input.getAttribute('value') || input.textContent || '';
                                    if (value) {
                                        // Ищем полную ссылку /cc/ с валидацией
                                        let match = value.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                                        if (match && match[1] && !match[1].startsWith('_0x') && match[1].length > 5) {
                                            const code = match[1];
                                            // Проверяем, что код не является зарезервированным словом
                                            if (!invalidCodes.includes(code.toLowerCase()) && 
                                                !code.includes('.') && !code.includes('/') && 
                                                !code.includes(':') && !code.startsWith('http')) {
                                                return 'https://market.yandex.ru/cc/' + code;
                                            }
                                        }
                                        // Ищем короткий код (например, 8FP5fa) с валидацией
                                        match = value.match(/\\b([A-Za-z][A-Za-z0-9_-]{4,19})\\b/);
                                        if (match && match[1] && !match[1].startsWith('_0x') && match[1].length >= 5 && match[1].length <= 20) {
                                            const code = match[1];
                                            // Проверяем, что это похоже на CC код
                                            if (!/^\\d+$/.test(code) && 
                                                !invalidCodes.includes(code.toLowerCase()) && 
                                                !code.includes('.') && !code.includes('/') && 
                                                !code.includes(':') && !code.startsWith('http')) {
                                                return 'https://market.yandex.ru/cc/' + code;
                                            }
                                        }
                                    }
                                }
                                
                                // 2. Ищем ссылку в тексте модального окна (включая скрытые элементы) с валидацией
                                const allText = modal.innerText || modal.textContent || '';
                                let match = allText.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                                if (match && match[1] && !match[1].startsWith('_0x') && match[1].length > 5) {
                                    const code = match[1];
                                    // Проверяем, что код не является зарезервированным словом или частью URL
                                    if (!invalidCodes.includes(code.toLowerCase()) && 
                                        !code.includes('.') && !code.includes('/') && 
                                        !code.includes(':') && !code.startsWith('http')) {
                                        // Проверяем контекст - не является ли это частью другого URL
                                        const codeIndex = allText.indexOf('https://market.yandex.ru/cc/' + code);
                                        if (codeIndex >= 0) {
                                            const before = allText.substring(Math.max(0, codeIndex - 20), codeIndex);
                                            const after = allText.substring(codeIndex + code.length + 30, Math.min(allText.length, codeIndex + code.length + 50));
                                            // Если после кода идет еще один URL, это ложное совпадение
                                            if (!after.match(/^[^\\s]*https?:/)) {
                                                return 'https://market.yandex.ru/cc/' + code;
                                            }
                                        }
                                    }
                                }
                                
                                // 3. Ищем ссылку в data-атрибутах всех элементов с валидацией
                                const allElements = modal.querySelectorAll('*');
                                for (const el of allElements) {
                                    const attrs = ['data-url', 'data-href', 'data-link', 'data-share-url', 'href', 'src'];
                                    for (const attr of attrs) {
                                        const href = el.getAttribute(attr);
                                        if (href) {
                                            match = href.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                                            if (match && match[1] && !match[1].startsWith('_0x') && match[1].length > 5) {
                                                const code = match[1];
                                                if (!invalidCodes.includes(code.toLowerCase()) && 
                                                    !code.includes('.') && !code.includes('/') && 
                                                    !code.includes(':') && !code.startsWith('http')) {
                                                    return 'https://market.yandex.ru/cc/' + code;
                                                }
                                            }
                                        }
                                    }
                                }
                                
                                // 4. Ищем ссылку в кнопках "Копировать" или "Скопировать" с валидацией
                                const copyButtons = modal.querySelectorAll('button, [role="button"], a');
                                for (const btn of copyButtons) {
                                    const btnText = btn.innerText || btn.textContent || '';
                                    if (btnText.includes('Копировать') || btnText.includes('Скопировать') || btnText.includes('Copy')) {
                                        // Проверяем data-атрибуты кнопки
                                        const btnHref = btn.getAttribute('data-url') || btn.getAttribute('data-href') || btn.getAttribute('data-link') || btn.getAttribute('href');
                                        if (btnHref) {
                                            match = btnHref.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                                            if (match && match[1] && !match[1].startsWith('_0x') && match[1].length > 5) {
                                                const code = match[1];
                                                if (!invalidCodes.includes(code.toLowerCase()) && 
                                                    !code.includes('.') && !code.includes('/') && 
                                                    !code.includes(':') && !code.startsWith('http')) {
                                                    return 'https://market.yandex.ru/cc/' + code;
                                                }
                                            }
                                        }
                                        // Проверяем родительский элемент
                                        const parent = btn.parentElement;
                                        if (parent) {
                                            const parentHref = parent.getAttribute('data-url') || parent.getAttribute('data-href') || parent.getAttribute('data-link');
                                            if (parentHref) {
                                                match = parentHref.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                                                if (match && match[1] && !match[1].startsWith('_0x') && match[1].length > 5) {
                                                    const code = match[1];
                                                    if (!invalidCodes.includes(code.toLowerCase()) && 
                                                        !code.includes('.') && !code.includes('/') && 
                                                        !code.includes(':') && !code.startsWith('http')) {
                                                        return 'https://market.yandex.ru/cc/' + code;
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                                
                                // 5. Ищем в HTML коде модального окна (включая скрытые элементы) с валидацией
                                const html = modal.innerHTML || '';
                                match = html.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                                if (match && match[1] && !match[1].startsWith('_0x') && match[1].length > 5) {
                                    const code = match[1];
                                    if (!invalidCodes.includes(code.toLowerCase()) && 
                                        !code.includes('.') && !code.includes('/') && 
                                        !code.includes(':') && !code.startsWith('http')) {
                                        return 'https://market.yandex.ru/cc/' + code;
                                    }
                                }
                                
                                // 6. #region agent edit - кликаем на кнопку "Копировать ссылку" и читаем из буфера обмена
                                // Убираем await из синхронной функции - используем промисы без await
                                const copyLinkButton = Array.from(copyButtons).find(btn => {
                                    const text = btn.innerText || btn.textContent || '';
                                    return text.includes('Копировать ссылку') || text.includes('Copy link') || text.includes('Копировать');
                                });
                                if (copyLinkButton) {
                                    try {
                                        copyLinkButton.click();
                                        // Не используем await в синхронной функции - просто кликаем
                                        // Чтение из буфера обмена будет выполнено через Playwright API
                                    } catch (e) {
                                        // Игнорируем ошибки
                                    }
                                }
                                // #endregion
                                
                                // #endregion
                                
                                return null;
                            }
                            """
                            try:
                                modal_link = await page.evaluate(modal_link_js)                                
                                # #region agent edit - если ссылка не найдена, пытаемся кликнуть на кнопку "Копировать ссылку" через Playwright
                                if not modal_link:
                                    try:
                                        # Ищем кнопку "Копировать ссылку" разными способами
                                        copy_link_button = None
                                        for selector in [
                                            'button:has-text("Копировать ссылку")',
                                            'button:has-text("Copy link")',
                                            'button:has-text("Копировать")',
                                            '[role="button"]:has-text("Копировать ссылку")',
                                            '[role="button"]:has-text("Копировать")'
                                        ]:
                                            try:
                                                copy_link_button = await page.query_selector(selector)
                                                if copy_link_button:                                                    break
                                            except Exception:
                                                continue
                                        
                                        if copy_link_button:
                                            # #region agent edit - МАКСИМАЛЬНО УЛУЧШЕННЫЙ СПОСОБ: используем все возможные методы получения ссылки
                                            try:
                                                # МЕТОД 1: Перехватываем событие copy через CDP перед кликом
                                                clipboard_captured = {"text": None}
                                                async def handle_copy_event(event):
                                                    try:
                                                        clipboard_captured["text"] = await page.evaluate("async () => { try { return await navigator.clipboard.readText(); } catch(e) { return null; } }")
                                                    except:
                                                        pass
                                                
                                                # МЕТОД 2: Устанавливаем перехватчик события copy через JavaScript
                                                await page.evaluate("""
                                                    () => {
                                                        // Сохраняем оригинальный обработчик
                                                        const originalWrite = document.execCommand;
                                                        document.execCommand = function(command, showUI, value) {
                                                            if (command === 'copy') {
                                                                setTimeout(() => {
                                                                    window.__copiedText = value || window.getSelection().toString();
                                                                }, 100);
                                                            }
                                                            return originalWrite.apply(this, arguments);
                                                        };
                                                        
                                                        // Перехватываем Clipboard API
                                                        const originalWriteText = navigator.clipboard.writeText;
                                                        navigator.clipboard.writeText = function(text) {
                                                            window.__copiedText = text;
                                                            return originalWriteText.apply(this, arguments);
                                                        };
                                                        
                                                        // Перехватываем событие copy
                                                        document.addEventListener('copy', function(e) {
                                                            const selection = window.getSelection().toString();
                                                            if (selection) {
                                                                window.__copiedText = selection;
                                                            }
                                                            if (e.clipboardData) {
                                                                const text = e.clipboardData.getData('text/plain');
                                                                if (text) {
                                                                    window.__copiedText = text;
                                                                }
                                                            }
                                                        }, true);
                                                    }
                                                """)
                                                
                                                # МЕТОД 3: Используем MutationObserver для отслеживания изменений в DOM
                                                await page.evaluate("""
                                                    () => {
                                                        if (!window.__linkObserver) {
                                                            window.__linkObserver = new MutationObserver(function(mutations) {
                                                                mutations.forEach(function(mutation) {
                                                                    mutation.addedNodes.forEach(function(node) {
                                                                        if (node.nodeType === 1) { // Element node
                                                                            const text = node.textContent || node.innerText || '';
                                                                            const match = text.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                                                                            if (match && match[1] && !match[1].startsWith('_0x') && match[1].length > 5) {
                                                                                window.__foundLink = 'https://market.yandex.ru/cc/' + match[1];
                                                                            }
                                                                            
                                                                            // Проверяем input поля
                                                                            if (node.tagName === 'INPUT' || node.tagName === 'TEXTAREA') {
                                                                                const value = node.value || node.getAttribute('value') || '';
                                                                                const match = value.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                                                                                if (match && match[1] && !match[1].startsWith('_0x') && match[1].length > 5) {
                                                                                    window.__foundLink = 'https://market.yandex.ru/cc/' + match[1];
                                                                                }
                                                                            }
                                                                        }
                                                                    });
                                                                });
                                                            });
                                                            
                                                            // Начинаем наблюдение за изменениями в модальном окне
                                                            const modal = document.querySelector('[role="dialog"]') || 
                                                                          document.querySelector('[class*="modal"]') || 
                                                                          document.querySelector('[class*="Modal"]');
                                                            if (modal) {
                                                                window.__linkObserver.observe(modal, {
                                                                    childList: true,
                                                                    subtree: true,
                                                                    attributes: true,
                                                                    attributeFilter: ['value', 'data-url', 'data-href', 'data-link']
                                                                });
                                                            }
                                                        }
                                                    }
                                                """)
                                                
                                                # МЕТОД 4: Кликаем через JavaScript
                                                await page.evaluate("""
                                                    (button) => {
                                                        if (button) {
                                                            button.click();
                                                        }
                                                    }
                                                """, copy_link_button)
                                                
                                                # МЕТОД 5: Ждем и проверяем все источники ссылки
                                                for wait_iteration in range(6):  # Проверяем 6 раз с интервалом 0.5 секунды
                                                    await asyncio.sleep(0.5)
                                                    
                                                    # Проверяем перехваченный текст из события copy
                                                    copied_text = await page.evaluate("() => window.__copiedText || null")
                                                    if copied_text:
                                                        cc_link = self._extract_cc_link(copied_text)
                                                        if cc_link:
                                                            captured["link"] = cc_link
                                                            logger.info(f"✅ Found link via copy event interception: {cc_link}")                                                            break
                                                    
                                                    # Проверяем ссылку, найденную через MutationObserver
                                                    found_link = await page.evaluate("() => window.__foundLink || null")
                                                    if found_link:
                                                        cc_link = self._extract_cc_link(found_link)
                                                        if cc_link:
                                                            captured["link"] = cc_link
                                                            logger.info(f"✅ Found link via MutationObserver: {cc_link}")                                                            break
                                                    
                                                    # Проверяем DOM модального окна
                                                    modal_link_after_click = await page.evaluate("""
                                                        () => {
                                                            const modal = document.querySelector('[role="dialog"]') || 
                                                                          document.querySelector('[class*="modal"]') || 
                                                                          document.querySelector('[class*="Modal"]');
                                                            if (!modal) return null;
                                                            
                                                            // Ищем ссылку во всех input полях
                                                            const inputs = modal.querySelectorAll('input, textarea');
                                                            for (const input of inputs) {
                                                                const value = input.value || input.getAttribute('value') || input.textContent || '';
                                                                if (value) {
                                                                    const match = value.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                                                                    if (match && match[1] && !match[1].startsWith('_0x') && match[1].length > 5) {
                                                                        return 'https://market.yandex.ru/cc/' + match[1];
                                                                    }
                                                                }
                                                            }
                                                            
                                                            // Ищем ссылку в тексте
                                                            const text = modal.innerText || modal.textContent || '';
                                                            const match = text.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                                                            if (match && match[1] && !match[1].startsWith('_0x') && match[1].length > 5) {
                                                                return 'https://market.yandex.ru/cc/' + match[1];
                                                            }
                                                            
                                                            return null;
                                                        }
                                                    """)
                                                    
                                                    if modal_link_after_click:
                                                        cc_link = self._extract_cc_link(modal_link_after_click)
                                                        if cc_link:
                                                            captured["link"] = cc_link
                                                            logger.info(f"✅ Found link in modal after copy button click: {cc_link}")                                                            break
                                                    
                                                    # Проверяем localStorage и sessionStorage
                                                    storage_link = await page.evaluate("""
                                                        () => {
                                                            try {
                                                                for (let i = 0; i < localStorage.length; i++) {
                                                                    const key = localStorage.key(i);
                                                                    const value = localStorage.getItem(key);
                                                                    const match = value.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                                                                    if (match && match[1] && !match[1].startsWith('_0x') && match[1].length > 5) {
                                                                        return 'https://market.yandex.ru/cc/' + match[1];
                                                                    }
                                                                }
                                                                for (let i = 0; i < sessionStorage.length; i++) {
                                                                    const key = sessionStorage.key(i);
                                                                    const value = sessionStorage.getItem(key);
                                                                    const match = value.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                                                                    if (match && match[1] && !match[1].startsWith('_0x') && match[1].length > 5) {
                                                                        return 'https://market.yandex.ru/cc/' + match[1];
                                                                    }
                                                                }
                                                            } catch(e) {}
                                                            return null;
                                                        }
                                                    """)
                                                    
                                                    if storage_link:
                                                        cc_link = self._extract_cc_link(storage_link)
                                                        if cc_link:
                                                            captured["link"] = cc_link
                                                            logger.info(f"✅ Found link in storage: {cc_link}")                                                            break
                                                    
                                                    # МЕТОД 7: Поиск ссылки в iframe (если модальное окно в iframe)
                                                    iframe_link = await page.evaluate("""
                                                        () => {
                                                            try {
                                                                const iframes = document.querySelectorAll('iframe');
                                                                for (const iframe of iframes) {
                                                                    try {
                                                                        const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                                                                        if (iframeDoc) {
                                                                            const text = iframeDoc.body.innerText || iframeDoc.body.textContent || '';
                                                                            const match = text.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                                                                            if (match && match[1] && !match[1].startsWith('_0x') && match[1].length > 5) {
                                                                                return 'https://market.yandex.ru/cc/' + match[1];
                                                                            }
                                                                            
                                                                            const inputs = iframeDoc.querySelectorAll('input, textarea');
                                                                            for (const input of inputs) {
                                                                                const value = input.value || input.getAttribute('value') || '';
                                                                                const match = value.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                                                                                if (match && match[1] && !match[1].startsWith('_0x') && match[1].length > 5) {
                                                                                    return 'https://market.yandex.ru/cc/' + match[1];
                                                                                }
                                                                            }
                                                                        }
                                                                    } catch(e) {}
                                                                }
                                                            } catch(e) {}
                                                            return null;
                                                        }
                                                    """)
                                                    
                                                    if iframe_link:
                                                        cc_link = self._extract_cc_link(iframe_link)
                                                        if cc_link:
                                                            captured["link"] = cc_link
                                                            logger.info(f"✅ Found link in iframe: {cc_link}")                                                            break
                                                    
                                                    # МЕТОД 8: Поиск ссылки в глобальных переменных JavaScript
                                                    global_link = await page.evaluate("""
                                                        () => {
                                                            try {
                                                                // Ищем в window объекте
                                                                for (const key in window) {
                                                                    try {
                                                                        const value = window[key];
                                                                        if (typeof value === 'string') {
                                                                            const match = value.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                                                                            if (match && match[1] && !match[1].startsWith('_0x') && match[1].length > 5) {
                                                                                return 'https://market.yandex.ru/cc/' + match[1];
                                                                            }
                                                                        } else if (typeof value === 'object' && value !== null) {
                                                                            const str = JSON.stringify(value);
                                                                            const match = str.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                                                                            if (match && match[1] && !match[1].startsWith('_0x') && match[1].length > 5) {
                                                                                return 'https://market.yandex.ru/cc/' + match[1];
                                                                            }
                                                                        }
                                                                    } catch(e) {}
                                                                }
                                                            } catch(e) {}
                                                            return null;
                                                        }
                                                    """)
                                                    
                                                    if global_link:
                                                        cc_link = self._extract_cc_link(global_link)
                                                        if cc_link:
                                                            captured["link"] = cc_link
                                                            logger.info(f"✅ Found link in global variables: {cc_link}")                                                            break
                                                    
                                                    if captured.get("link"):
                                                        break
                                                
                                                # МЕТОД 6: Пытаемся прочитать из буфера обмена (последняя попытка)
                                                if not captured.get("link"):
                                                    try:
                                                        clipboard_text = await page.evaluate("async () => { try { return await navigator.clipboard.readText(); } catch(e) { return null; } }")
                                                        if clipboard_text:
                                                            cc_link = self._extract_cc_link(clipboard_text)
                                                            if cc_link:
                                                                captured["link"] = cc_link
                                                                logger.info(f"✅ Found link in clipboard after copy button click: {cc_link}")                                                    except Exception as e:
                                                        logger.debug(f"⚠️ Failed to read clipboard: {e}")                                                
                                                if captured.get("link"):
                                                    break
                                                    
                                            except Exception as e:
                                                logger.debug(f"⚠️ Failed to click copy button via JS: {e}")                                            # #endregion
                                        else:                                    except Exception as e:
                                        logger.debug(f"⚠️ Failed to click copy button: {e}")                                # #endregion
                                
                                if modal_link:
                                    cc_link = self._extract_cc_link(modal_link)                                    if cc_link:
                                        captured["link"] = cc_link
                                        logger.info(f"✅ Found link in modal via JavaScript: {cc_link}")                                        # Прерываем цикл проверки модального окна, так как ссылка найдена
                                        break
                                else:                            except Exception as e:
                                logger.debug(f"⚠️ Failed to find link in modal via JavaScript: {e}")                            # #endregion
                            # Прерываем цикл проверки модального окна
                            break
                    
                    # Если модальное окно не найдено через JavaScript, пробуем через Playwright
                    if not modal_found:
                        logger.debug("⚠️ Modal not found via JavaScript, trying Playwright selectors...")
                        await asyncio.wait_for(
                            page.wait_for_selector(
                                ', '.join(SHARE_MODAL_SELECTORS) if SHARE_MODAL_SELECTORS else '[role="dialog"], [data-testid*="modal"], [class*="Modal"]',
                                state='visible',
                                timeout=5000  # 5 секунд для быстрой проверки
                            ),
                            timeout=5.0
                        )
                        logger.debug("✅ Share modal appeared via Playwright")
                        modal_found = True
                except asyncio.TimeoutError:
                    logger.warning("⚠️ Share modal did not appear within 45s, continuing with DOM search...")                except Exception as e:
                    logger.debug(f"⚠️ Modal wait error: {e}, continuing...")                # #endregion
                
                # Wait a bit for modal to stabilize
                await asyncio.sleep(random.uniform(0.5, 1.0))
                
                # Try to click "Copy link" button if available
                copy_button = await self._find_copy_button(page)
                if copy_button:
                    try:
                        # Make button visible via JavaScript (fix for display=flex, visibility=hidden)
                        await page.evaluate("""
                            (button) => {
                                if (button) {
                                    button.style.display = 'flex';
                                    button.style.visibility = 'visible';
                                    button.style.opacity = '1';
                                    // Also check parent elements
                                    let parent = button.parentElement;
                                    while (parent && parent !== document.body) {
                                        parent.style.display = parent.style.display || 'block';
                                        parent.style.visibility = 'visible';
                                        parent.style.opacity = '1';
                                        parent = parent.parentElement;
                                    }
                                }
                            }
                        """, copy_button)
                        logger.debug("✅ Made copy button visible via JS")
                        
                        await copy_button.click(timeout=3000)
                        await asyncio.sleep(random.uniform(0.3, 0.6))  # Wait for copy action
                        logger.debug("✅ Clicked 'Copy link' button")
                    except Exception as e:
                        logger.debug(f"⚠️ Failed to click copy button: {e}")
                
                # Try clipboard first (after copy button click)
                clipboard_link = await self._try_clipboard_read(page)
                if clipboard_link:
                    captured["link"] = clipboard_link
                    logger.info(f"✅ Found link via clipboard: {clipboard_link}")
                    break
                
                # If clipboard failed, search DOM
                dom_link = await self._try_dom_search(page)
                if dom_link:
                    captured["link"] = dom_link
                    logger.info(f"✅ Found link via DOM search: {dom_link}")                    break
                
                # #region agent edit - если модальное окно не появилось, пробуем найти ссылку в DOM без модального окна
                # Иногда ссылка может быть в DOM даже без модального окна
                if not modal_found:
                    logger.debug("⚠️ Modal not found, trying to find link in DOM without modal...")
                    # Ищем ссылку напрямую в DOM через JavaScript
                    dom_link_js = """
                    () => {
                        // Ищем все ссылки с /cc/ в href или data-атрибутах
                        const links = document.querySelectorAll('a[href*="/cc/"], [data-href*="/cc/"], [data-url*="/cc/"]');
                        for (const link of links) {
                            const href = link.href || link.getAttribute('data-href') || link.getAttribute('data-url');
                            if (href && href.includes('/cc/')) {
                                const match = href.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                                if (match && match[1] && !match[1].startsWith('_0x')) {
                                    return 'https://market.yandex.ru/cc/' + match[1];
                                }
                            }
                        }
                        // Ищем в тексте страницы
                        const text = document.body.innerText || document.body.textContent || '';
                        const match = text.match(/https?:\\/\\/market\\.yandex\\.ru\\/cc\\/([A-Za-z0-9_-]+)/);
                        if (match && match[1] && !match[1].startsWith('_0x')) {
                            return 'https://market.yandex.ru/cc/' + match[1];
                        }
                        return null;
                    }
                    """
                    try:
                        js_link = await page.evaluate(dom_link_js)
                        if js_link:
                            cc_link = self._extract_cc_link(js_link)
                            if cc_link:
                                captured["link"] = cc_link
                                logger.info(f"✅ Found link via JavaScript DOM search (without modal): {cc_link}")                                break
                    except Exception as e:
                        logger.debug(f"⚠️ JavaScript DOM search failed: {e}")
                # #endregion
                
                # Wait before retry (human-like delay)
                if attempt < self.max_retries - 1:
                    retry_delay = random.uniform(RETRY_DELAY_MIN, RETRY_DELAY_MAX)
                    logger.debug(f"⏳ Waiting {retry_delay:.2f}s before retry...")
                    await asyncio.sleep(retry_delay)
                
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"⚠️ Button click attempt {attempt + 1} failed: {e}", exc_info=True)
                if attempt < self.max_retries - 1:
                    retry_delay = random.uniform(RETRY_DELAY_MIN, RETRY_DELAY_MAX)
                    await asyncio.sleep(retry_delay)
        
        return captured.get("link")
    
    async def _find_copy_button(self, page) -> Optional[Any]:
        """
        Find "Copy link" button in share modal.
        
        Args:
            page: Playwright page object
            
        Returns:
            Copy button element if found, None otherwise
        """
        try:
            for selector in COPY_LINK_BUTTON_SELECTORS:
                try:
                    button = await asyncio.wait_for(
                        page.query_selector(selector),
                        timeout=2.0
                    )
                    if button:
                        # Check if button is visible
                        is_visible = await button.is_visible()
                        if is_visible:
                            logger.debug(f"✅ Found copy button: {selector}")
                            return button
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
        except Exception as e:
            logger.debug(f"Copy button search failed: {e}")
        
        return None
    
    async def _try_clipboard_read(self, page) -> Optional[str]:
        """
        Try to read CC link from clipboard after "Share → Copy link" action.
        Uses navigator.clipboard.readText() API with fallback to execCommand.
        
        Args:
            page: Playwright page object
            
        Returns:
            CC link if found in clipboard, None otherwise
        """
        try:
            logger.debug("📋 Attempting to read clipboard...")
            
            # Method 1: Try navigator.clipboard.readText() (modern API)
            try:
                clipboard_content = await page.evaluate("""
                    async () => {
                        try {
                            if (navigator.clipboard && navigator.clipboard.readText) {
                                const text = await navigator.clipboard.readText();
                                return text;
                            }
                            return null;
                        } catch (e) {
                            return null;
                        }
                    }
                """)
                
                if clipboard_content:
                    cc_link = self._extract_cc_link(clipboard_content)
                    if cc_link:
                        logger.info(f"✅ Found CC link in clipboard (navigator.clipboard): {cc_link}")
                        return cc_link
            except Exception as e:
                logger.debug(f"⚠️ navigator.clipboard.readText() failed: {e}, trying fallback...")
            
            # Method 2: Fallback to execCommand('paste') - deprecated but works in Playwright
            try:
                clipboard_content = await page.evaluate("""
                    () => {
                        return new Promise((resolve) => {
                            try {
                                const textArea = document.createElement('textarea');
                                textArea.style.position = 'fixed';
                                textArea.style.left = '-999999px';
                                textArea.style.top = '-999999px';
                                document.body.appendChild(textArea);
                                textArea.focus();
                                textArea.select();
                                
                                try {
                                    const success = document.execCommand('paste');
                                    if (success) {
                                        const text = textArea.value;
                                        document.body.removeChild(textArea);
                                        resolve(text);
                                    } else {
                                        document.body.removeChild(textArea);
                                        resolve(null);
                                    }
                                } catch (e) {
                                    document.body.removeChild(textArea);
                                    resolve(null);
                                }
                            } catch (e) {
                                resolve(null);
                            }
                        });
                    }
                """)
                
                if clipboard_content:
                    cc_link = self._extract_cc_link(clipboard_content)
                    if cc_link:
                        logger.info(f"✅ Found CC link in clipboard (execCommand fallback): {cc_link}")
                        return cc_link
                    else:
                        logger.debug(f"⚠️ Clipboard (execCommand) contains text but no CC link: {clipboard_content[:100]}")
            except Exception as e:
                logger.debug(f"⚠️ execCommand('paste') fallback failed: {e}")
            
            logger.debug("⚠️ Clipboard is empty or not accessible via both methods")
                
        except Exception as e:
            logger.debug(f"⚠️ Clipboard read failed: {e}")
        
        return None
    
    async def _try_dom_search(self, page) -> Optional[str]:
        """
        Search DOM for CC links in share modal.
        Searches: input values, hidden anchors, data-attributes.
        
        Args:
            page: Playwright page object
            
        Returns:
            CC link if found in DOM, None otherwise
        """
        try:
            logger.debug("🔍 Searching DOM for CC link...")
            
            # Search DOM for CC links in various locations
            dom_result = await page.evaluate("""
                () => {
                    const results = {
                        input_values: [],
                        anchor_hrefs: [],
                        data_attributes: [],
                        text_content: []
                    };
                    
                    // 1. Search input values in share modal
                    const inputs = document.querySelectorAll('input[type="text"], input[type="url"], input[readonly], input[value*="cc"], input[value*="market.yandex.ru"]');
                    inputs.forEach(input => {
                        const value = input.value || input.getAttribute('value');
                        if (value) {
                            results.input_values.push(value);
                        }
                    });
                    
                    // 2. Search hidden anchors or links
                    const anchors = document.querySelectorAll('a[href*="cc"], a[href*="market.yandex.ru"], a[data-href*="cc"]');
                    anchors.forEach(anchor => {
                        const href = anchor.href || anchor.getAttribute('href') || anchor.getAttribute('data-href');
                        if (href) {
                            results.anchor_hrefs.push(href);
                        }
                    });
                    
                    // 3. Search data-attributes
                    const dataElements = document.querySelectorAll('[data-url*="cc"], [data-link*="cc"], [data-shorturl*="cc"], [data-href*="cc"], [data-cc*="cc"]');
                    dataElements.forEach(el => {
                        // Check all data-* attributes
                        Array.from(el.attributes).forEach(attr => {
                            if (attr.name.startsWith('data-') && attr.value) {
                                results.data_attributes.push(attr.value);
                            }
                        });
                    });
                    
                    // 4. Search text content in share modal (might contain link as text)
                    const shareModals = document.querySelectorAll('[role="dialog"], .modal, [class*="modal"], [class*="share"], [class*="Share"]');
                    shareModals.forEach(modal => {
                        const text = modal.textContent || modal.innerText;
                        if (text) {
                            // Extract URLs from text
                            const urlRegex = /https?:\/\/[^\s<>"{}|\\^`\[\]]+/gi;
                            const urls = text.match(urlRegex);
                            if (urls) {
                                results.text_content.push(...urls);
                            }
                        }
                    });
                    
                    return results;
                }
            """)
            
            # Search through all found values
            all_values = (
                dom_result.get("input_values", []) +
                dom_result.get("anchor_hrefs", []) +
                dom_result.get("data_attributes", []) +
                dom_result.get("text_content", [])
            )
            
            for value in all_values:
                if isinstance(value, str):
                    # #region agent edit - ДОПОЛНИТЕЛЬНАЯ ВАЛИДАЦИЯ: проверяем источник перед извлечением
                    # Пропускаем значения, которые явно не являются CC ссылками
                    if 'partner.market.yandex.ru' in value or 'passport.yandex.ru' in value:
                        continue  # Пропускаем ссылки на партнерский портал и паспорт
                    # #endregion
                    
                    cc_link = self._extract_cc_link(value)
                    if cc_link:
                        # #region agent edit - ДОПОЛНИТЕЛЬНАЯ ВАЛИДАЦИЯ: проверяем извлеченную ссылку
                        # Проверяем, что код не является зарезервированным словом
                        if '/cc/' in cc_link:
                            code = cc_link.split('/cc/')[1].split('?')[0].split('#')[0].split(',')[0].strip()
                            invalid_codes = ['partner', 'passport', 'auth', 'login', 'register', 'account', 'profile', 'settings', 'help', 'support', 'about', 'contact', 'terms', 'privacy', 'cookie', 'policy', 'legal', 'faq', 'blog', 'news', 'press', 'careers', 'https', 'http', 'www', 'market', 'yandex', 'ru', 'special', 'originals', 'card', 'product', 'catalog', 'search', 'shop', 'seller', 'offer', 'price', 'review', 'rating', 'image', 'photo', 'video']
                            if code.lower() in invalid_codes:
                                logger.debug(f"⚠️ Skipping invalid CC code from DOM: {code} (source: {value[:100]})")
                                continue
                        # #endregion
                        
                        logger.info(f"✅ Found CC link in DOM: {cc_link} (source: {value[:100]})")
                        return cc_link
            
            logger.debug(f"⚠️ DOM search found {len(all_values)} potential values but no CC link")
            
        except Exception as e:
            logger.debug(f"⚠️ DOM search failed: {e}")
        
        return None
    
    async def _get_cookies_from_context(self, context) -> Dict[str, str]:
        """Extract cookies from browser context as dict for httpx."""
        try:
            cookies = await context.cookies()
            return {c.get('name', ''): c.get('value', '') for c in cookies if c.get('name')}
        except Exception:
            return {}
    
    async def _save_storage_state(self, context, url: str, only_if_success: bool = False):
        """
        Сохраняет storage state (cookies, localStorage) для повторного использования.
        
        Args:
            context: Playwright browser context
            url: URL для определения имени файла
            only_if_success: Сохранять только если операция успешна
        """
        try:
            # Check if context has cookies (indicates successful session)
            cookies = await context.cookies()
            if not cookies and only_if_success:
                # No cookies, skip saving
                return
            
            domain = urlparse(url).netloc
            fingerprint = hash(domain) % STORAGE_STATE_HASH_MOD
            state_path = STORAGE_STATE_DIR / f"{fingerprint}.json"
            
            # Check if state already exists and is recent (avoid unnecessary writes)
            if state_path.exists():
                stat = state_path.stat()
                age = time.time() - stat.st_mtime
                if age < 300:  # Less than 5 minutes old
                    logger.debug(f"⏭️ Storage state is recent, skipping save")
                    return
            
            await context.storage_state(path=str(state_path))
            logger.info(f"💾 Saved storage state: {state_path}")
        except Exception as e:
            logger.warning(f"Failed to save storage state: {e}")
    
    async def generate(
        self,
        url: str,
        job_id: Optional[str] = None,
        reuse_state_path: Optional[str] = None,
        cancellation_token: Optional[asyncio.CancelledError] = None
    ) -> str:
        """
        Generate partner link for Yandex Market product.
        
        Args:
            url: Product URL
            job_id: Optional job identifier for debug artifacts
            reuse_state_path: Optional path to storage state file to reuse
            cancellation_token: Optional cancellation token for async cancellation
            
        Returns:
            Clean partner link (https://market.yandex.ru/cc/XXXXX)
            
        Raises:
            LinkGenerationError: If link cannot be generated
            ConfigurationError: If inputs are invalid
            asyncio.CancelledError: If operation is cancelled
        """
        # Validate inputs
        from src.utils.input_validators import validate_link_generation_inputs
        
        is_valid, error = validate_link_generation_inputs(
            url=url,
            job_id=job_id,
            timeout=self.timeout,
            max_retries=self.max_retries,
            reuse_state_path=reuse_state_path
        )
        if not is_valid:
            raise ConfigurationError(
                f"Invalid input parameters: {error}",
                debug_path=None,
                job_id=job_id,
                url=url
            )
        
        if not job_id:
            job_id = f"job_{int(time.time())}"
        
        # Check cancellation
        if cancellation_token:
            raise asyncio.CancelledError("Operation cancelled")
        
        # Check if URL already contains /cc/ (valid partner link format)
        # NOTE: We check for /cc/ in path, NOT cc= parameter (which is old/debug only)
        cc_match = re.search(r'/cc/([A-Za-z0-9_-]+)', url)
        if cc_match:
            cc_code = cc_match.group(1)
            logger.info(f"✅ URL already contains /cc/ link: https://market.yandex.ru/cc/{cc_code}")
            return f"https://market.yandex.ru/cc/{cc_code}"
        
        # DEBUG: Check for old cc= parameter (for debug info only, never use as final link)
        cc_param_match = re.search(r'[?&]cc=([A-Za-z0-9_-]+)', url)
        if cc_param_match:
            old_cc_code = cc_param_match.group(1)
            logger.debug(f"⚠️ Found old cc= parameter in URL (DEBUG ONLY, not using): {old_cc_code}")
            # Do NOT use this as final link - it's likely outdated or incorrect
        
        # STEP 1: Try official Distribution method
        distribution_link = await self._try_distribution_method(url)
        if distribution_link:
            return distribution_link
        
        # STEP 2: PRIMARY METHOD - Try cached XHR reproduction (NO BROWSER NEEDED)
        # This is the fastest path: pure HTTP client, no rendering
        logger.info("🔄 STEP 2: Trying cached XHR reproduction (PRIMARY METHOD - no browser)...")
        try:
            from src.utils.xhr_cache import get_xhr_cache
            from src.utils.xhr_reproducer import reproduce_xhr_directly, extract_short_url_from_response
            
            cache = get_xhr_cache()
            cached_xhr = await cache.get(url)
            
            if cached_xhr:
                logger.info("📦 Found cached XHR, reproducing via httpx (pure HTTP, no browser)...")
                
                # Use random UA from pool for anti-detection
                user_agent = random.choice(USER_AGENTS)
                
                # Reproduce XHR directly (no browser context needed)
                response_data = await asyncio.wait_for(
                    reproduce_xhr_directly(
                        cached_xhr,
                        cookies=None,  # Cookies should be in cached_xhr headers
                        timeout=XHR_REPRODUCTION_TIMEOUT,
                        product_url=url,
                        user_agent=user_agent
                    ),
                    timeout=XHR_REPRODUCTION_TIMEOUT + 5.0
                )
                
                if response_data:
                    link = extract_short_url_from_response(response_data)
                    if link:
                        logger.info(f"✅ Link obtained via cached XHR reproduction (PRIMARY METHOD): {link}")
                        return link
                    else:
                        logger.debug("⚠️ Cached XHR reproduced but no CC link found in response")
                else:
                    logger.debug("⚠️ Cached XHR reproduction returned no data")
            else:
                logger.debug("📦 No cached XHR found, will capture via Playwright")
        except asyncio.TimeoutError:
            logger.warning("⚠️ XHR reproduction (cache) timed out, continuing to Playwright fallback")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug(f"XHR reproduction (cache) failed: {e}, continuing to Playwright fallback")
        
        # STEP 3: FALLBACK - Use Playwright to capture XHR (if cache miss or cache failed)
        # Initialize variables for cleanup
        browser = None
        context = None
        page = None
        pool = None
        captured = None
        
        try:
            from playwright.async_api import async_playwright, TimeoutError as PWTimeout
        except ImportError:
            raise ConfigurationError(
                "Playwright not installed. Run: pip install playwright && python -m playwright install chromium",
                debug_path=None,
                job_id=job_id,
                url=url
            )
        
        async with async_playwright() as pw:            try:
                # Use context pool for better performance
                from src.utils.context_pool import get_context_pool
                
                # Rotate UA and viewport BEFORE creating context (ensures they're applied)
                user_agent = random.choice(USER_AGENTS)
                viewport = random.choice(VIEWPORTS)
                
                logger.info(f"🔄 STEP 3: Using Playwright fallback (UA: {user_agent[:50]}...)")
                logger.debug(f"🔄 Using viewport: {viewport}")
                
                # Проверяем, нужно ли использовать браузер Yandex с существующим профилем                import src.config as config
                use_yandex_profile = getattr(config, 'USE_YANDEX_BROWSER_PROFILE', False)
                yandex_user_data_dir = getattr(config, 'YANDEX_BROWSER_USER_DATA_DIR', '')
                yandex_executable_path = getattr(config, 'YANDEX_BROWSER_EXECUTABLE_PATH', '')
                connect_to_existing = getattr(config, 'CONNECT_TO_EXISTING_BROWSER', False)
                existing_browser_cdp_url = getattr(config, 'EXISTING_BROWSER_CDP_URL', '')                
                browser = None
                is_connected_browser = False  # Флаг для отслеживания подключения к существующему браузеру                
                # #region agent edit - ВСЕГДА пытаемся подключиться к браузеру через CDP ПЕРВЫМ делом
                # Вариант 1: Подключиться к запущенному браузеру через CDP
                # Пытаемся подключиться даже если connect_to_existing=False, так как браузер запускается при старте бота
                cdp_url_to_try = existing_browser_cdp_url if existing_browser_cdp_url else 'http://127.0.0.1:9222'
                # ВСЕГДА пытаемся подключиться через CDP - это приоритетный способ
                logger.info(f"🔗 Attempting to connect to browser via CDP: {cdp_url_to_try}")                try:
                    browser = await pw.chromium.connect_over_cdp(cdp_url_to_try)
                    is_connected_browser = True
                    logger.info("✅ Connected to existing browser via CDP - will use existing browser window")                except Exception as e:
                    logger.error(f"❌ Failed to connect to existing browser via CDP: {e}")
                    logger.error(f"❌ Browser must be running with --remote-debugging-port=9222")
                    logger.error(f"❌ Will NOT launch new browser to avoid creating second window")                    browser = None
                    is_connected_browser = False
                    # НЕ запускаем новый браузер - это создаст второе окно
                    # Вместо этого выдаем ошибку
                # #endregion
                
                # Вариант 2: Использовать user data directory браузера Yandex
                # ВАЖНО: Этот вариант ПОЛНОСТЬЮ ОТКЛЮЧЕН - мы ВСЕГДА используем CDP подключение
                # Если CDP не работает, выдаем ошибку, а не запускаем новый браузер
                # Это предотвращает создание второго окна браузера
                # КОД ОТКЛЮЧЕН - НЕ ЗАПУСКАЕМ НОВЫЙ БРАУЗЕР
                if False:  # ВСЕГДА False - этот блок никогда не выполнится
                    logger.warning("⚠️ CDP connection failed, but attempting to use Yandex profile - this may create a second browser window")                    logger.info(f"🌐 Using Yandex browser profile: {yandex_user_data_dir}")                    try:
                        from pathlib import Path
                        import shutil
                        user_data_path = Path(yandex_user_data_dir)
                        if not user_data_path.exists():
                            logger.warning(f"⚠️ Yandex user data directory not found: {yandex_user_data_dir}, using default")
                            browser = await pw.chromium.launch(
                                headless=self.headless and not self.debug,
                                args=BROWSER_LAUNCH_ARGS,
                                executable_path=yandex_executable_path if yandex_executable_path else None
                            )
                        else:
                            # Используем launch_persistent_context для работы с user data directory
                            # Это позволяет использовать user data directory даже если браузер уже запущен
                            logger.info("✅ Using Yandex browser user data directory with launch_persistent_context")                            # Используем launch_persistent_context - это правильный способ работы с user data directory
                            # Persistent context создает BrowserContext напрямую, но нам нужен Browser для pool
                            # Решение: используем launch с правильными параметрами, но с отдельным профилем
                            # чтобы избежать конфликта с запущенным браузером
                            try:
                                # Пробуем использовать оригинальный профиль напрямую через launch_persistent_context
                                # Это позволит использовать cookies и авторизацию из основного браузера
                                logger.info(f"📋 Using original Yandex profile: {user_data_path}")                                persistent_context = await pw.chromium.launch_persistent_context(
                                    user_data_dir=str(user_data_path),
                                    headless=self.headless and not self.debug,
                                    executable_path=yandex_executable_path if yandex_executable_path else None,
                                    args=BROWSER_LAUNCH_ARGS,
                                )
                                # Получаем browser из persistent context
                                browser = persistent_context.browser
                                if browser:
                                    logger.info("✅ Browser obtained from persistent context (original profile)")                                else:
                                    logger.warning("⚠️ Browser not available from persistent context")
                                    browser = None
                            except Exception as persistent_error:
                                logger.warning(f"⚠️ Failed to use launch_persistent_context: {persistent_error}")                                # Если persistent context не может быть запущен (например, браузер уже использует user_data_dir),
                                # пробуем использовать обычный launch с отдельным профилем
                                logger.info("⚠️ Persistent context failed, trying regular launch with separate profile...")
                                try:
                                    import tempfile
                                    temp_profile = Path(tempfile.gettempdir()) / "yandex_bot_profile_separate"
                                    if not temp_profile.exists():
                                        # Копируем cookies и localStorage из Default профиля
                                        default_profile = user_data_path / "Default"
                                        if default_profile.exists():
                                            logger.info(f"📋 Copying profile data to separate profile: {temp_profile}")
                                            try:
                                                temp_profile.mkdir(parents=True, exist_ok=True)
                                                for item in ["Cookies", "Local Storage", "Session Storage", "Preferences", "Login Data"]:
                                                    src = default_profile / item
                                                    if src.exists():
                                                        if src.is_file():
                                                            shutil.copy2(src, temp_profile / item)
                                                        elif src.is_dir():
                                                            shutil.copytree(src, temp_profile / item, dirs_exist_ok=True)
                                                logger.info("✅ Profile data copied to separate profile")
                                            except Exception as copy_error:
                                                logger.warning(f"⚠️ Failed to copy profile: {copy_error}")
                                    # Используем отдельный профиль через обычный launch
                                    browser = await pw.chromium.launch(
                                        headless=self.headless and not self.debug,
                                        executable_path=yandex_executable_path if yandex_executable_path else None,
                                        args=BROWSER_LAUNCH_ARGS + [f'--user-data-dir={temp_profile}'],
                                    )
                                    logger.info("✅ Browser launched with separate profile")
                                except Exception as e2:
                                    logger.warning(f"⚠️ Failed to use separate profile: {e2}")
                                    browser = None
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to use Yandex browser profile: {e}, using default")                        browser = None
                
                # Вариант 3: Обычный запуск (по умолчанию)
                # ВАЖНО: Этот вариант НЕ должен выполняться, если CDP подключение не удалось
                # потому что это создаст второе окно браузера
                if browser is None:
                    error_msg = (
                        "❌ Cannot connect to existing browser via CDP and will NOT launch new browser "
                        "to avoid creating second window. "
                        "Please ensure browser is running with --remote-debugging-port=9222"
                    )
                    logger.error(error_msg)                    raise LinkGenerationError(
                        error_msg,
                        debug_path=None,
                        job_id=job_id,
                        url=url
                    )                
                pool = get_context_pool()
                storage_state_path = self._get_storage_state_path_for_reuse(url, reuse_state_path)                
                # Acquire context with UA rotation (ensured by pool)
                # Убеждаемся, что storage_state_path не пустой (не None и не пустая строка)
                actual_storage_state_path = storage_state_path if (storage_state_path and storage_state_path.strip()) else None                
                context = await pool.acquire(
                    browser,
                    storage_state_path=actual_storage_state_path,
                    viewport=viewport,
                    user_agent=user_agent,
                    locale=BROWSER_LOCALE,
                    timezone_id=BROWSER_TIMEZONE,
                    permissions=BROWSER_PERMISSIONS,
                )                
                # #region agent edit - при использовании существующего CDP контекста используем существующие страницы или создаем новую
                # Проверяем, есть ли уже открытые страницы в контексте
                existing_pages = context.pages if hasattr(context, 'pages') else []
                skip_navigation = False
                if existing_pages and is_connected_browser:
                    # Используем первую существующую страницу из контекста
                    page = existing_pages[0]
                    current_page_url = page.url if hasattr(page, 'url') else ''
                    # Проверяем, не открыта ли уже нужная страница
                    from urllib.parse import urlparse
                    current_path = urlparse(current_page_url).path
                    target_path = urlparse(url).path
                    if current_path == target_path:
                        logger.info(f"✅ Page already on target URL, skipping navigation: {current_page_url[:100]}")
                        skip_navigation = True
                    else:
                        logger.info(f"✅ Using existing page from CDP context (page URL: {current_page_url[:100]})")                else:
                    # Создаем новую страницу
                    logger.info("🆕 Creating new page in context")                    page = await context.new_page()
                # #endregion                
                # Apply stealth and anti-detection (ALWAYS, even if stealth plugin fails)
                await self._apply_stealth_and_anti_detection(page, context)
                
                # Network interception - captured data
                # IMPORTANT: Interception is enabled BEFORE any button clicks
                captured = {
                    "link": None,
                    "response_data": None,
                    "xhr_info": None,
                    "network_dump": []
                }
                
                self._setup_network_interception(page, captured, job_id=job_id)
                
                # Check cancellation before expensive operations
                if cancellation_token:
                    raise asyncio.CancelledError("Link generation cancelled")
                
                # Navigate to page (with retry logic and timeout)
                # #region agent edit - пропускаем навигацию, если страница уже на нужном URL
                if skip_navigation:
                    logger.info("⏭️ Skipping navigation - page already on target URL")
                    navigation_success = True
                else:
                    logger.info(f"📄 Navigating to: {url}")                    navigation_success = False
                    for nav_attempt in range(3):  # Retry navigation up to 3 times
                        try:
                            # #region agent edit - проверяем captured["link"] во время навигации и прерываем, если найдена
                            # Используем более короткий таймаут и проверяем captured["link"] каждые 2 секунды
                            nav_timeout = min(30000, self.timeout * 1000)  # 30 секунд максимум для навигации
                            navigation_task = asyncio.create_task(
                                page.goto(url, wait_until='domcontentloaded', timeout=nav_timeout)
                            )
                            
                            # #region agent edit - НЕ прерываем навигацию, если найдена ссылка
                            # Ссылка, найденная во время навигации, может быть неправильной (например, CgAQVxgQIL2g-wEonrc4gH3m7QY)
                            # Правильная ссылка должна извлекаться через клик на кнопку "Поделиться" и модальное окно
                            # Поэтому мы НЕ прерываем навигацию, а продолжаем выполнение до клика на кнопку "Поделиться"
                            # Просто ждем завершения навигации
                            await navigation_task
                            navigation_success = True
                            # #endregion
                            # #endregion                            if navigation_success:
                                break
                        except asyncio.TimeoutError:
                            if nav_attempt < 2:
                                wait_time = 2 ** nav_attempt  # 1s, 2s
                                logger.warning(f"⚠️ Navigation timeout (attempt {nav_attempt + 1}/3), retrying in {wait_time}s...")
                                await asyncio.sleep(wait_time)
                            else:
                                # Убеждаемся, что DEBUG_DIR существует
                                DEBUG_DIR.mkdir(exist_ok=True, parents=True)
                                raise LinkTimeoutError(
                                    f"Page navigation timed out after {self.timeout}s (3 attempts)",
                                    debug_path=str(DEBUG_DIR / job_id) if DEBUG_DIR else None,
                                    original_error=None,
                                    job_id=job_id,
                                    url=url
                                )
                        except Exception as e:
                            error_str = str(e)
                            if nav_attempt < 2 and ("netERRABORTED" in error_str or "frame was detached" in error_str):
                                wait_time = 2 ** nav_attempt
                                logger.warning(f"⚠️ Navigation error (attempt {nav_attempt + 1}/3): {e}, retrying in {wait_time}s...")
                                await asyncio.sleep(wait_time)
                            else:
                                raise
                # #endregion
                
                if not navigation_success:
                    # Убеждаемся, что DEBUG_DIR существует
                    DEBUG_DIR.mkdir(exist_ok=True, parents=True)
                    raise LinkTimeoutError(
                        f"Page navigation failed after 3 attempts",
                        debug_path=str(DEBUG_DIR / job_id) if DEBUG_DIR else None,
                        original_error=None,
                        job_id=job_id,
                        url=url
                    )
                
                # Проверяем, залогинен ли пользователь
                login_required = await self._check_login_required(page, job_id)
                if login_required and not self.headless:
                    logger.warning("⚠️ Требуется вход в аккаунт. Браузер видимый - войдите вручную.")
                    logger.warning("   После входа состояние будет сохранено автоматически.")
                    # Ждем, пока пользователь войдет (проверяем каждые 5 секунд)
                    for attempt in range(60):  # Максимум 5 минут
                        await asyncio.sleep(5)
                        login_required = await self._check_login_required(page, job_id)
                        if not login_required:
                            logger.info("✅ Вход выполнен, сохраняю состояние...")
                            # Сохраняем состояние после логина
                            await self._save_storage_state(context, url, only_if_success=True)
                            break
                        if attempt % 6 == 0:  # Каждые 30 секунд
                            logger.info(f"⏳ Ожидаю входа... (попытка {attempt + 1}/60)")
                    if login_required:
                        logger.warning("⚠️ Вход не выполнен, продолжаю без сохранения состояния")
                
                # Check for CAPTCHA after navigation
                captcha_detected = await self._check_and_handle_captcha(page, job_id)
                if captcha_detected:
                    # Если CAPTCHA обнаружена, но браузер видимый и мы уже ждали её решения,
                    # то _check_and_handle_captcha вернет False после решения
                    # Если вернула True, значит CAPTCHA не решена или браузер headless
                    if not self.headless:
                        # В видимом браузере мы уже ждали решения в _check_and_handle_captcha
                        # Если вернула True, значит timeout или ошибка
                        logger.warning("⚠️ CAPTCHA не решена в течение 5 минут, но продолжаю попытку...")
                        # Не выбрасываем исключение, продолжаем работу (может быть, CAPTCHA решится позже)
                    else:
                        # В headless режиме выбрасываем исключение
                        raise CaptchaError(
                            "CAPTCHA detected - manual intervention required (headless mode)",
                            debug_path=str(DEBUG_DIR / job_id),
                            job_id=job_id,
                            url=url
                        )
                
                # Check cancellation after navigation
                if cancellation_token:
                    raise asyncio.CancelledError("Link generation cancelled after navigation")
                
                # #region agent edit - даем время обработчику сетевого перехвата сохранить ссылку
                # Небольшая задержка, чтобы обработчик сетевого перехвата успел обработать все ответы
                await asyncio.sleep(1.0)
                # #endregion
                
                # #region agent edit - НЕ возвращаем ссылку, найденную во время навигации
                # Ссылка, найденная во время навигации, может быть неправильной (например, CgAQVxgQIL2g-wEonrc4gH3m7QY)
                # Правильная ссылка должна извлекаться через клик на кнопку "Поделиться" и модальное окно
                # Поэтому мы НЕ возвращаем ссылку здесь, а продолжаем выполнение до клика на кнопку "Поделиться"
                if captured["link"]:
                    logger.warning(f"⚠️ Found link during navigation, but ignoring it (will get correct link via Share button): {captured['link']}")                    # Очищаем captured["link"], чтобы продолжить выполнение до клика на кнопку "Поделиться"
                    captured["link"] = None
                logger.debug("⚠️ No link captured during navigation (or ignored), will try Share button click method")                # #endregion
                
                # STEP 4: Try XHR reproduction if we captured one during navigation
                if captured.get("xhr_info"):
                    logger.info("🔄 STEP 4: Trying XHR reproduction with captured XHR...")
                    try:
                        from src.utils.xhr_reproducer import reproduce_xhr_directly, extract_short_url_from_response
                        from src.utils.xhr_cache import get_xhr_cache
                        
                        # Get cookies from context
                        cookies_dict = await self._get_cookies_from_context(context)
                        
                        # Reproduce XHR directly (pure HTTP, no browser needed for this step)
                        response_data = await asyncio.wait_for(
                            reproduce_xhr_directly(
                                captured["xhr_info"],
                                cookies=cookies_dict,
                                timeout=XHR_REPRODUCTION_TIMEOUT,
                                product_url=url,
                                user_agent=user_agent
                            ),
                            timeout=XHR_REPRODUCTION_TIMEOUT + 5.0
                        )
                        
                        if response_data:
                            link = extract_short_url_from_response(response_data)
                            if link:
                                logger.info(f"✅ Link obtained via captured XHR reproduction: {link}")
                                # Cache successful XHR for future use
                                cache = get_xhr_cache()
                                await cache.put(url, captured["xhr_info"])
                                # Save network dump before returning
                                await self._save_network_dump(captured, job_id=job_id)
                                await self._save_storage_state(context, url, only_if_success=True)
                                await pool.release(context, reuse=True)
                                if not is_connected_browser:
                                    await browser.close()
                                return link
                    except asyncio.TimeoutError:
                        logger.warning("⚠️ XHR reproduction (captured) timed out, continuing to button click")
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.debug(f"XHR reproduction (captured) failed: {e}, continuing to button click")
                
                # STEP 5: FALLBACK - Click "Share" button with retries (last resort)
                try:
                    button_link = await asyncio.wait_for(
                        self._try_button_click(page, captured, cancellation_token),
                        timeout=self.timeout
                    )
                    if button_link:
                        # Save network dump before returning
                        await self._save_network_dump(captured, job_id=job_id)
                        await self._save_storage_state(context, url, only_if_success=True)
                        await pool.release(context, reuse=True)
                        if not is_connected_browser:
                            await browser.close()
                        return button_link
                except asyncio.TimeoutError:
                    logger.warning("⚠️ Button click timed out")
                except asyncio.CancelledError:
                    raise
                except ButtonNotFoundError:
                    raise  # Re-raise as-is
                except Exception as e:
                    logger.warning(f"Button click failed: {e}", exc_info=True)
                
                # All attempts failed
                error_msg = (
                    f"No link captured after all attempts. "
                    f"Tried: Distribution method, XHR cache, network interception, "
                    f"XHR reproduction, and button click ({self.max_retries} retries)."
                )
                # Save network dump before saving debug artifacts
                await self._save_network_dump(captured, job_id=job_id)
                await self._save_debug_artifacts(
                    page, job_id, error_msg, captured.get("xhr_info") if captured else None
                )
                await pool.release(context, reuse=False)  # Don't reuse failed context
                if not is_connected_browser:
                    await browser.close()
                raise LinkGenerationError(
                    error_msg,
                    xhr_info=captured.get("xhr_info") if captured else None,
                    debug_path=str(DEBUG_DIR / job_id),
                    job_id=job_id,
                    url=url
                )
                
            except PWTimeout as e:
                error_msg = (
                    f"Playwright timeout after {self.timeout}s. "
                    f"This may indicate network issues, page load problems, or server overload."
                )
                # Save network dump if available
                if 'captured' in locals() and captured:
                    await self._save_network_dump(captured, job_id=job_id)
                await self._save_debug_artifacts(
                    page, job_id, error_msg, captured.get("xhr_info") if 'captured' in locals() and captured else None
                )
                if context and pool:
                    await pool.release(context, reuse=False)
                if browser and not is_connected_browser:
                    await browser.close()
                raise LinkTimeoutError(
                    error_msg,
                    xhr_info=captured.get("xhr_info") if captured else None,
                    debug_path=str(DEBUG_DIR / job_id),
                    original_error=e,
                    job_id=job_id,
                    url=url
                ) from e
                
            except ButtonNotFoundError as e:
                # Enhance error message
                if not e.debug_path:
                    e.debug_path = str(DEBUG_DIR / job_id)
                e.job_id = job_id
                e.url = url
                
                # Save network dump if available
                if 'captured' in locals() and captured:
                    await self._save_network_dump(captured, job_id=job_id)
                await self._save_debug_artifacts(
                    page, job_id, f"Button not found: {e.message}", 
                    captured.get("xhr_info") if 'captured' in locals() and captured else None
                )
                if context and pool:
                    await pool.release(context, reuse=False)
                if browser and not is_connected_browser:
                    await browser.close()
                raise
                
            except asyncio.CancelledError:
                # Save debug artifacts even on cancellation
                if 'captured' in locals() and captured:
                    await self._save_network_dump(captured, job_id=job_id)
                if page:
                    await self._save_debug_artifacts(
                        page, job_id, "Operation cancelled",
                        captured.get("xhr_info") if 'captured' in locals() and captured else None
                    )
                if context and pool:
                    await pool.release(context, reuse=False)
                if browser and not is_connected_browser:
                    await browser.close()
                raise
                
            except Exception as e:
                # Save debug artifacts on ANY exception
                if 'captured' in locals() and captured:
                    await self._save_network_dump(captured, job_id=job_id)
                if page:
                    await self._save_debug_artifacts(
                        page, job_id, str(e),
                        captured.get("xhr_info") if 'captured' in locals() and captured else None
                    )
                elif browser:
                    # Even if page wasn't created, try to save what we can
                    try:
                        # Убеждаемся, что DEBUG_DIR существует
                        DEBUG_DIR.mkdir(exist_ok=True, parents=True)
                        error_log_path = DEBUG_DIR / f"{job_id}_error.txt"
                        error_log_path.write_text(
                            f"Error before page creation: {e}\n"
                            f"Job ID: {job_id}\n"
                            f"URL: {url}\n"
                            f"Timestamp: {time.time()}\n",
                            encoding="utf-8"
                        )
                    except Exception:
                        pass
                
                if context and pool:
                    await pool.release(context, reuse=False)
                if browser:
                    await browser.close()
                
                # Classify error with enhanced messages
                error_str = str(e).lower()
                error_type = type(e).__name__
                
                if "timeout" in error_str or "timed out" in error_str:
                    raise LinkTimeoutError(
                        f"Timeout during link generation: {error_type} - {e}. "
                        f"Operation exceeded {self.timeout}s timeout.",
                        debug_path=str(DEBUG_DIR / job_id),
                        original_error=e,
                        job_id=job_id,
                        url=url
                    ) from e
                elif any(keyword in error_str for keyword in ["404", "403", "429", "5xx", "http"]):
                    status_code = None
                    if "404" in error_str:
                        status_code = 404
                    elif "403" in error_str:
                        status_code = 403
                    elif "429" in error_str:
                        status_code = 429
                    raise HTTPError(
                        f"HTTP error ({status_code or 'unknown'}): {error_type} - {e}. "
                        f"Server returned an error response.",
                        status_code=status_code,
                        debug_path=str(DEBUG_DIR / job_id),
                        original_error=e,
                        job_id=job_id,
                        url=url
                    ) from e
                elif "captcha" in error_str or "капча" in error_str:
                    raise CaptchaError(
                        f"Captcha detected: {error_type} - {e}. "
                        f"Yandex requires captcha verification. Manual intervention may be needed.",
                        debug_path=str(DEBUG_DIR / job_id),
                        original_error=e,
                        job_id=job_id,
                        url=url
                    ) from e
                elif "throttl" in error_str or "rate limit" in error_str:
                    raise ThrottlingError(
                        f"Rate limiting detected: {error_type} - {e}. "
                        f"Too many requests. Please wait before retrying.",
                        debug_path=str(DEBUG_DIR / job_id),
                        original_error=e,
                        job_id=job_id,
                        url=url
                    ) from e
                else:
                    raise LinkGenerationError(
                        f"Unexpected error during link generation: {error_type} - {e}. "
                        f"Check debug artifacts for details.",
                        xhr_info=captured.get("xhr_info") if captured else None,
                        debug_path=str(DEBUG_DIR / job_id),
                        original_error=e,
                        job_id=job_id,
                        url=url
                    ) from e

# Export for backward compatibility
__all__ = ['YandexMarketLinkGen', 'RefLinkGenerationError']
