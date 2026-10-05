"""
AcadAlly Automizer

"""
import time
import base64
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException, JavascriptException
import json
import sys
import os
import traceback


class AcadallyBot:
    def __init__(self, nvidia_api_key):
        self.nvidia_api_key = nvidia_api_key
        self.driver = None

    def bring_browser_to_foreground(self):
        """On Windows: try to bring the Chrome window that Selenium is
        driving to the foreground and restore it if minimized. This is
        critical because:
          - is_displayed() / getBoundingClientRect() return zeros when
            Chrome is minimized or another app has focus
          - scrollIntoView and synthetic event dispatchers are ignored
            when the tab is in the background

        Uses Selenium's window_handles + native Win32 API via ctypes.
        On non-Windows platforms this is a no-op.
        """
        try:
            if self.driver is None:
                return False
        except Exception:
            return False
        # First: use Chrome's own DevTools protocol to ask it to bring
        # the tab to focus. Works even if the whole window is minimized.
        try:
            for handle in self.driver.window_handles:
                try:
                    self.driver.switch_to.window(handle)
                    break
                except Exception:
                    pass
        except Exception:
            pass
        try:
            # CDP Browser.bringToFront - restores window + focuses tab
            self.driver.execute_cdp_cmd("Browser.bringToFront", {})
            time.sleep(0.3)
        except Exception:
            pass
        # Second: attempt a JavaScript-level window.focus + blur/restore
        # to make the page think it is in the foreground.
        try:
            self.driver.execute_script(
                "try { window.focus(); "
                "Object.defineProperty(document, 'hidden', {value:false, configurable:true}); "
                "Object.defineProperty(document, 'visibilityState', {value:'visible', configurable:true}); "
                "document.dispatchEvent(new Event('visibilitychange')); "
                "window.dispatchEvent(new Event('focus')); "
                "document.dispatchEvent(new Event('focus')); } catch(e) {}"
            )
        except Exception:
            pass
        # Third: Windows-native restore + SetForegroundWindow by matching
        # the window title that Selenium/Chrome exposes.
        if sys.platform.startswith("win"):
            try:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32
                SW_RESTORE = 9
                SW_SHOW = 5
                EnumWindows = user32.EnumWindows
                EnumWindowsProc = ctypes.WINFUNCTYPE(
                    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
                )
                GetWindowTextW = user32.GetWindowTextW
                GetWindowTextLengthW = user32.GetWindowTextLengthW
                IsWindowVisible = user32.IsWindowVisible
                IsIconic = user32.IsIconic
                ShowWindow = user32.ShowWindow
                SetForegroundWindow = user32.SetForegroundWindow
                AllowSetForegroundWindow = user32.AllowSetForegroundWindow
                GetWindowThreadProcessId = user32.GetWindowThreadProcessId
                try:
                    pid = self.driver.service.process.pid if self.driver and self.driver.service else 0
                except Exception:
                    pid = 0
                found_hwnds = []
                def _cb(hwnd, lparam):
                    if not IsWindowVisible(hwnd):
                        return True
                    length = GetWindowTextLengthW(hwnd)
                    if length == 0:
                        return True
                    buf = ctypes.create_unicode_buffer(length + 1)
                    GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value or ""
                    wpid = wintypes.DWORD()
                    GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
                    own_pid_match = (pid and wpid.value == pid)
                    chrome_match = (
                        ("Google Chrome" in title)
                        or ("Chrome" in title and ("AcadAlly" in title or "leap.acadally" in title or "app.acadally" in title))
                        or ("AcadAlly" in title)
                    )
                    if own_pid_match or chrome_match:
                        found_hwnds.append(hwnd)
                    return True
                EnumWindows(EnumWindowsProc(_cb), 0)
                if not found_hwnds and pid:
                    # Fallback: any window whose process PID equals our Chrome's.
                    def _cb2(hwnd, lparam):
                        wpid = wintypes.DWORD()
                        GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
                        if wpid.value == pid and IsWindowVisible(hwnd):
                            found_hwnds.append(hwnd)
                        return True
                    EnumWindows(EnumWindowsProc(_cb2), 0)
                for hwnd in found_hwnds:
                    try:
                        if IsIconic(hwnd):
                            ShowWindow(hwnd, SW_RESTORE)
                        else:
                            ShowWindow(hwnd, SW_SHOW)
                        try:
                            AllowSetForegroundWindow(-1)
                        except Exception:
                            pass
                        SetForegroundWindow(hwnd)
                        time.sleep(0.15)
                    except Exception:
                        pass
            except Exception:
                pass
        time.sleep(0.4)
        return True

    def setup_driver(self):
        """Setup Chrome driver and open Acadally"""
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("--disable-gcm")
        chrome_options.add_argument("--disable-sync")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--no-first-run")
        # Prevent the tab from being throttled in the background; makes
        # scrollIntoView, timers, and event dispatchers work even if
        # another app steals focus briefly.
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-window-activation")
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Open Acadally website
        print("Opening app.acadally.com...")
        self.driver.get("https://app.acadally.com")
        return True
    
    def wait_for_user_ready(self):
        """Wait for user to login and start the quiz"""
        print("\n" + "="*50)
        print("🤖 ACADALLY BOT READY")
        print("="*50)
        print("Please manually:")
        print("1. Login to your account (if not already logged in)")
        print("2. Navigate to your quiz")
        print("3. Start the quiz and get to the first question")
        print("4. Come back here and press Enter to continue")
        print("="*50)
        
        input("Press Enter when you're on the first question...")
        return True
    
    def take_question_screenshot(self):
        """Take in-memory-only screenshot (bytes) of the current page.
        No files are written to disk; screenshot is stored exclusively in
        runtime memory. Wait for answer controls so a slow network does not
        send a loading screen to the AI.
        """
        try:
            print("   ⏳ Waiting for the question and answer options to finish loading...")
            end_at = time.time() + 45
            while time.time() < end_at:
                ready = bool(self.driver.execute_script(
                    """
                    function visible(el) {
                      if (!el || !el.offsetParent) return false;
                      var s = getComputedStyle(el);
                      return s.display !== 'none' && s.visibility !== 'hidden';
                    }
                    var loading = Array.from(document.querySelectorAll(
                      '[class*="loading" i], [class*="spinner" i], [class*="skeleton" i]'
                    )).some(visible);
                    if (loading) return false;
                    var cards = Array.from(document.querySelectorAll('div.options > div.option-card'))
                      .filter(visible);
                    var labelledCards = cards.filter(function(card) {
                      var label = card.querySelector('.option-label-box');
                      var text = label ? (label.innerText || label.textContent || '').trim() : '';
                      return /^[A-D]$/.test(text);
                    });
                    if (labelledCards.length >= 2) return true;
                    var inputs = Array.from(document.querySelectorAll(
                      'input[type="radio"], input[type="checkbox"]'
                    )).filter(visible);
                    return inputs.length >= 2;
                    """
                ))
                if ready:
                    break
                time.sleep(0.35)
            else:
                print("⚠️  Question controls did not finish loading within 45 seconds.")
                return None
            screenshot_bytes = self.driver.get_screenshot_as_png()
            return screenshot_bytes
        except Exception as e:
            print(f"Error taking screenshot: {e}")
            return None

    def _extract_answer_letter(self, answer_text):
        """Parse an A/B/C/D answer out of raw model response text.

        Designed for direct-answer VLMs (meta/llama-3.2-11b-vision-instruct)
        which normally reply with a single letter like "C". Also handles:
          - stray labeled anchors ("FINAL ANSWER: C", "Answer is B")
          - accidental wrapper text ("I think the answer is D.")
          - leftover <think>...</think> wrapper (safety strip)
        """
        import re

        if not answer_text:
            return None

        text = answer_text.strip()

        # Safety strip any stray XML-style thinking wrapper (rare on Llama 3.2)
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()

        if not text:
            return None

        # 1) Single letter on its own (normal / expected path)
        m = re.match(r'^\s*([A-D])\s*$', text, re.IGNORECASE)
        if m:
            return ord(m.group(1).upper()) - ord('A') + 1

        # 2) Labeled anchor: "FINAL ANSWER: C" / "Answer = B" / etc.
        label_kw = r'(?:FINAL\s*ANSWER|ANSWER|OPTION|CHOICE|LETTER|CORRECT\s*ANSWER|THE\s*ANSWER\s*IS)'
        m = re.search(label_kw + r'\s*[:=\-\)]?\s*([A-D])', text, re.IGNORECASE)
        if m:
            return ord(m.group(1).upper()) - ord('A') + 1

        # 3) Loose: take the LAST standalone A/B/C/D letter anywhere in text
        letters = re.findall(r'\b([A-D])\b', text, re.IGNORECASE)
        if letters:
            return ord(letters[-1].upper()) - ord('A') + 1

        return None

    def get_ai_answer_from_screenshot(self, screenshot_bytes):
        """Send in-memory screenshot to NVIDIA NIM multimodal API
        using meta/muse-glimmer-30b.

        Muse Glimmer is a multimodal REASONING model with SEPARATE
        reasoning output: the chain-of-thought lives in message.reasoning
        and the final answer lives in message.content. We NEVER read from
        message.reasoning, so letters mentioned during deliberation can't
        leak into the extracted answer.
        503/429 overload errors are retried with short exponential backoff.
        No disk writes at any point.
        """
        try:
            if screenshot_bytes is None:
                print("❌ No screenshot bytes available")
                return None

            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            print(f"📸 In-memory screenshot captured ({len(screenshot_bytes)} bytes)")

            strict_prompt = (
                "You are solving a multiple-choice quiz shown in the attached image. "
                "Read the question and all 4 options (A, B, C, D) carefully and determine the correct answer. "
                "You may think things through in your reasoning area, but the final answer text must be only ONE letter. "
                "FINAL ANSWER FORMAT (non-negotiable): Reply with ONLY a single uppercase character A, B, C, or D. "
                "No extra words, no explanation, no sentences, no prefix, no quotes, no markdown, no blank lines. "
                "That one letter must be the very last character in your final answer."
            )

            stream = False
            payload = {
                "model": "meta/muse-glimmer-30b",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": strict_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
                            },
                        ],
                    }
                ],
                "max_tokens": 2048,
                "stream": stream,
                "temperature": 0.6,
                "top_p": 0.95,
            }

            headers = {
                "Authorization": f"Bearer {self.nvidia_api_key}",
                "Accept": "application/json",
            }

            invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"

            answer_text = ""
            reasoning_text = ""
            finish_reason = "(unknown)"
            usage = {}

            max_retries = 4
            backoff_seconds = 3
            _t0 = time.time()
            print(f"🤖 Calling meta/muse-glimmer-30b (NIM multimodal reasoning)...")
            for attempt in range(1, max_retries + 1):
                try:
                    # Muse Glimmer 30B is a dense 30B reasoning model on free
                    # tier cold-start worker; allow a generous but bounded
                    # per-attempt window.
                    response = requests.post(
                        invoke_url, headers=headers, json=payload, stream=stream, timeout=300
                    )
                    if response.status_code == 200:
                        _elapsed = time.time() - _t0
                        result = response.json() or {}
                        choice = (result.get("choices") or [{}])[0]
                        msg = choice.get("message") or {}
                        # Muse Glimmer on NIM separates output into:
                        #   message.content   -> final answer area (ideal)
                        #   message.reasoning -> chain-of-thought area
                        # On the free tier the engine often dumps the ONLY
                        # answer into the reasoning field, leaving content
                        # empty. So we prefer content but will fall back to
                        # extracting a letter from reasoning if content is
                        # empty AND the reasoning text has a valid answer.
                        _content = msg.get("content", "") or ""
                        _reasoning = msg.get("reasoning", "") or ""
                        finish_reason = choice.get("finish_reason", "(unknown)")
                        usage = result.get("usage") or {}
                        print(f"   ⏱️  API call took ~{_elapsed:.0f}s (attempt {attempt}/{max_retries}), content_len={len(_content)}, reasoning_len={len(_reasoning)}, finish={finish_reason}")
                        if len(_content) == 0 and attempt < max_retries:
                            # NIM free-tier worker often emits empty content
                            # with populated reasoning on the 1st try and a
                            # proper content answer on the 2nd. Retry fast.
                            print(f"   ⚠️  Empty content on attempt {attempt}. Retrying in {backoff_seconds}s...")
                            time.sleep(backoff_seconds)
                            backoff_seconds *= 2
                            continue
                        answer_text = _content
                        reasoning_text = _reasoning
                        break
                    _is_soft = response.status_code in (503, 429)
                    if (
                        (_is_soft or response.status_code in (502, 504))
                        and attempt < max_retries
                        and (_is_soft or attempt < 3)
                    ):
                        print(
                            f"   ⚠️  HTTP {response.status_code} on attempt {attempt}/{max_retries}. "
                            f"Waiting {backoff_seconds}s then retrying... ({response.text[:120]})"
                        )
                        time.sleep(backoff_seconds)
                        backoff_seconds *= 2
                        continue
                    print(f"❌ NVIDIA NIM API HTTP {response.status_code}: {response.text[:500]}")
                    return None
                except requests.exceptions.RequestException as e:
                    if attempt < max_retries:
                        print(
                            f"   ⚠️  Network error on attempt {attempt}/{max_retries}: {e}. "
                            f"Waiting {backoff_seconds}s then retrying..."
                        )
                        time.sleep(backoff_seconds)
                        backoff_seconds *= 2
                        continue
                    print(f"❌ Network error calling NVIDIA NIM: {e}")
                    return None
            else:
                print(f"❌ All {max_retries} API attempts failed.")
                return None

            if usage:
                print(
                    f"   📊 Usage: prompt_tokens={usage.get('prompt_tokens')}, "
                    f"completion_tokens={usage.get('completion_tokens')}, "
                    f"finish_reason={finish_reason}"
                )

            print(f"🤖 RAW content:   {repr(answer_text[:500])}")

            answer_num = self._extract_answer_letter(answer_text)
            extraction_source = "content"

            # Primary (content) extraction failed. As a last-ditch fall-back,
            # the NIM free tier sometimes hides the ONLY letter inside the
            # separate `message.reasoning` field. Try extracting there too.
            if answer_num is None and reasoning_text:
                print(f"   ℹ️  content had no answer; trying reasoning field...")
                answer_num = self._extract_answer_letter(reasoning_text)
                extraction_source = "reasoning (FALLBACK)"

            if answer_num is not None:
                letter = chr(ord("A") + answer_num - 1)
                print(f"✅ Extracted answer: Option {letter} (Number {answer_num}) from {extraction_source}")
                return answer_num

            print(f"❌ Could not extract valid A/B/C/D answer from response (content_len={len(answer_text)}, reasoning_len={len(reasoning_text)})")
            return None

        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"❌ Error getting AI answer: {e}")
            return None
    
    def select_answer_with_visual_feedback(self, option_number):
        """Select answer with multiple attempts and visual feedback check"""
        try:
            print(f"🎯 Attempting to select option {option_number}")
            option_letter = chr(64 + option_number)  # 1->A, 2->B, etc.
            
            # Take a screenshot before selection to compare later
            before_screenshot = None
            try:
                before_screenshot = self.driver.get_screenshot_as_png()
            except:
                pass
            
            # Strategy 1: Try to find radio buttons/checkboxes
            try:
                inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
                if option_number <= len(inputs):
                    input_elem = inputs[option_number-1]
                    
                    # Try multiple click methods
                    click_methods = [
                        lambda: self.driver.execute_script("arguments[0].click();", input_elem),
                        lambda: input_elem.click(),
                        lambda: self.driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", input_elem),
                        lambda: self.driver.execute_script("arguments[0].dispatchEvent(new Event('click'));", input_elem)
                    ]
                    
                    for method in click_methods:
                        try:
                            method()
                            print(f"✅ Clicked input element {option_number}")
                            time.sleep(0.5)
                            
                            # Check if input is now selected
                            if input_elem.get_attribute('checked'):
                                print("✅ Selection confirmed - input is checked")
                                return True
                        except:
                            continue
            except Exception as e:
                print(f"Input method failed: {e}")
            
            # Strategy 2: Look for elements with the option letter
            letter_patterns = [
                f"//*[contains(text(), '{option_letter}.')]",
                f"//*[contains(text(), '{option_letter})')]",
                f"//*[contains(text(), 'Option {option_letter}')]",
                f"//*[starts-with(text(), '{option_letter}.')]",
                f"//*[starts-with(text(), '{option_letter})')]",
                f"//*[contains(., '{option_letter}') and contains(@class, 'option')]"
            ]
            
            for pattern in letter_patterns:
                try:
                    elements = self.driver.find_elements(By.XPATH, pattern)
                    for elem in elements:
                        if elem.is_displayed():
                            # Try clicking the element
                            self.driver.execute_script("arguments[0].click();", elem)
                            print(f"✅ Clicked element with pattern: {pattern}")
                            time.sleep(0.5)
                            
                            # Try to find if any parent element now has selected class
                            parent = elem
                            for _ in range(3):  # Check up to 3 parent levels
                                try:
                                    parent = parent.find_element(By.XPATH, "..")
                                    classes = parent.get_attribute('class') or ''
                                    if 'selected' in classes.lower() or 'active' in classes.lower():
                                        print("✅ Found 'selected' class on parent")
                                        return True
                                except:
                                    break
                            
                            # Check the element itself for selected class
                            elem_classes = elem.get_attribute('class') or ''
                            if 'selected' in elem_classes.lower() or 'active' in elem_classes.lower():
                                print("✅ Found 'selected' class on element")
                                return True
                except:
                    continue
            
            # Strategy 3: Look for answer containers
            try:
                # Find all containers that might hold answers
                containers = self.driver.find_elements(By.CSS_SELECTOR, 
                    "[class*='answer'], [class*='option'], [class*='choice'], .quiz-option, .question-option")
                
                if option_number <= len(containers):
                    container = containers[option_number-1]
                    
                    # Try clicking at different positions within container
                    click_points = [
                        lambda: self.driver.execute_script("arguments[0].click();", container),
                        lambda: container.click(),
                        lambda: self.driver.execute_script("""
                            var rect = arguments[0].getBoundingClientRect();
                            var x = rect.left + rect.width/2;
                            var y = rect.top + rect.height/2;
                            var ev = new MouseEvent('click', {
                                view: window,
                                bubbles: true,
                                cancelable: true,
                                clientX: x,
                                clientY: y
                            });
                            arguments[0].dispatchEvent(ev);
                        """, container)
                    ]
                    
                    for method in click_points:
                        try:
                            method()
                            print(f"✅ Clicked answer container {option_number}")
                            time.sleep(0.5)
                            
                            # Check container for selected state
                            container_classes = container.get_attribute('class') or ''
                            if 'selected' in container_classes.lower() or 'active' in container_classes.lower():
                                print("✅ Container shows as selected")
                                return True
                        except:
                            continue
            except Exception as e:
                print(f"Container method failed: {e}")
            
            # Strategy 4: Try clicking by position (fallback)
            print("⚠️ Trying positional click as last resort...")
            try:
                # Find all interactive elements
                interactive = self.driver.find_elements(By.CSS_SELECTOR, 
                    "div, label, li, button, [role='button'], [tabindex]")
                
                # Filter to likely answer elements
                answer_candidates = []
                for elem in interactive:
                    try:
                        if elem.is_displayed() and elem.is_enabled():
                            text = elem.text.strip()
                            if text and len(text) < 150:  # Not too long
                                answer_candidates.append(elem)
                    except:
                        continue
                
                if option_number <= len(answer_candidates):
                    elem = answer_candidates[option_number-1]
                    self.driver.execute_script("arguments[0].click();", elem)
                    print(f"✅ Positional click on element {option_number}")
                    return True
            except Exception as e:
                print(f"Positional click failed: {e}")
            
            # If we get here, ask user to verify
            print("\n⚠️  WARNING: Cannot confirm if answer was selected!")
            print("⚠️  Please check if option is selected in the browser.")
            print("⚠️  If not selected, please click it manually.")
            time.sleep(2)  # Give user time to see the message
            
            # Continue anyway - user can manually correct if needed
            return True
            
        except Exception as e:
            print(f"❌ Error selecting answer: {e}")
            return False
    
    def navigate_to_next(self):
        """Click next button or submit"""
        try:
            # Try Next button with various selectors
            next_selectors = [
                "//button[contains(., 'Next')]",
                "//button[contains(., 'NEXT')]",
                "//button[contains(., 'Next Question')]",
                "//input[@value='Next']",
                "//*[contains(@class, 'next')]",
                "//*[contains(@class, 'next-btn')]",
                "//button[contains(@class, 'next')]",
                "//a[contains(., 'Next')]"
            ]
            
            for xpath in next_selectors:
                try:
                    button = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH, xpath))
                    )
                    self.driver.execute_script("arguments[0].click();", button)
                    print("✅ Clicked Next button")
                    time.sleep(3)  # Wait for next question to load
                    return "next"
                except:
                    continue
            
            # Try Submit button (last question)
            submit_selectors = [
                "//button[contains(., 'Submit')]",
                "//button[contains(., 'SUBMIT')]",
                "//button[contains(., 'Finish')]",
                "//input[@value='Submit']",
                "//*[contains(@class, 'submit')]",
                "//button[contains(@class, 'submit')]"
            ]
            
            for xpath in submit_selectors:
                try:
                    button = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH, xpath))
                    )
                    self.driver.execute_script("arguments[0].click();", button)
                    print("🎉 Clicked Submit button - Quiz completed!")
                    return "submit"
                except:
                    continue
            
            print("❌ Could not find Next/Submit button")
            return "unknown"
            
        except Exception as e:
            print(f"Error navigating: {e}")
            return "error"
    
    def handle_scrolling(self):
        """Scroll to ensure all content is visible"""
        try:
            # Scroll to make options visible
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
            time.sleep(0.5)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)
        except Exception as e:
            print(f"Error handling scroll: {e}")
    
    def check_if_quiz_ended(self):
        """Check if quiz has ended"""
        try:
            # Look for completion messages
            end_indicators = [
                "//*[contains(., 'Quiz Completed')]",
                "//*[contains(., 'Score:')]",
                "//*[contains(., 'Results')]",
                "//*[contains(., 'Congratulations')]",
                "//*[contains(., 'Finished')]"
            ]
            
            for xpath in end_indicators:
                try:
                    if self.driver.find_element(By.XPATH, xpath):
                        print("📊 Quiz appears to be completed!")
                        return True
                except:
                    continue
            return False
        except:
            return False

    # ------------------------------------------------------------------
    # Batch (All Quizzes) helpers - CSS selectors only.
    # None of these are invoked in Single-Quiz mode, so the original
    # single-quiz flow remains 100% identical.
    # ------------------------------------------------------------------

    def confirm_submit_popup(self, timeout_s=12):
        """Click the positive button in the post-Submit confirmation.

        Used only by All-Quizzes mode.  It uses DOM text rather than the
        unsupported Selenium CSS :has-text() pseudo-selector.
        """
        print("   🛎️  Looking for post-Submit confirmation...")
        end_at = time.time() + timeout_s
        while time.time() < end_at:
            try:
                label = self.driver.execute_script(
                    """
                    function usable(el) {
                      if (el.disabled || !el.offsetParent) return false;
                      var s = getComputedStyle(el);
                      return s.display !== 'none' && s.visibility !== 'hidden';
                    }
                    function textOf(el) {
                      return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
                    }
                    function positive(text) {
                      return text === 'submit' || text === 'submit quiz' ||
                             text === 'confirm' || text === 'yes' ||
                             text === 'yes, submit' || text === 'yes submit';
                    }
                    function rank(el) {
                      var score = 0, node = el;
                      for (var i=0; i<12 && node; i++, node=node.parentElement) {
                        var cls = (node.className || '').toString().toLowerCase();
                        var style = getComputedStyle(node);
                        if (node.getAttribute('role') === 'dialog' || node.getAttribute('aria-modal') === 'true' ||
                            /modal|popup|dialog|confirm|overlay/.test(cls)) score += 10000;
                        if (style.position === 'fixed') score += 5000;
                        var z = parseInt(style.zIndex, 10);
                        if (!isNaN(z)) score += Math.min(z, 1000);
                      }
                      return score;
                    }
                    var all = Array.from(document.querySelectorAll('button, [role="button"], input[type="button"], input[type="submit"]'));
                    var matches = all.filter(function(el) { return usable(el) && positive(textOf(el)); });
                    if (!matches.length) return null;
                    matches.sort(function(a,b) { return rank(b)-rank(a) || all.indexOf(b)-all.indexOf(a); });
                    var button = matches[0];
                    var label = textOf(button);
                    button.click();
                    return label;
                    """
                )
            except Exception:
                label = None
            if label:
                print(f"   ✅ Clicked post-Submit confirmation: {label}")
                time.sleep(1.0)
                return True
            time.sleep(0.25)
        print("   ⚠️  Post-Submit confirmation is not visible yet.")
        return False

    def wait_for_results_page_and_go_back(self, timeout_s=20):
        """Finish the batch-only completion path.

        Acadally may show Continue after confirmation, or go straight to
        Go to Journey. Browser history is intentionally never used here.
        """
        end_at = time.time() + timeout_s
        while time.time() < end_at:
            try:
                action = self.driver.execute_script(
                    """
                    function usable(button) {
                      return !button.disabled && !!button.offsetParent;
                    }
                    function textOf(button) {
                      return (button.innerText || button.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
                    }
                    var buttons = Array.from(document.querySelectorAll('button, [role="button"], a')).filter(usable);
                    var journey = buttons.find(function(button) { return textOf(button) === 'go to journey'; });
                    if (journey) { journey.click(); return 'go to journey'; }
                    var proceed = buttons.find(function(button) { return textOf(button) === 'continue'; });
                    if (proceed) { proceed.click(); return 'continue'; }
                    return null;
                    """
                )
            except Exception:
                action = None
            if action == "continue":
                print("   ▶️  Clicked Continue after submission")
                time.sleep(0.8)
            elif action == "go to journey":
                print("   🧭 Clicked Go to Journey and returned to the quest menu")
                time.sleep(2)
                return True
            else:
                time.sleep(0.25)
        print("   ⚠️  Go to Journey is not visible yet; remaining on the completion flow.")
        return False

    def find_and_click_next_quest_card(self):
        """Find and click an incomplete quest card by image-src matching.

        KEY FIXES for "page closes in 2 seconds / didn't scroll" class of
        issues:
          - NEVER raise exceptions out of this function (outer loop would
            hit the `break` → browser closed immediately). Wraps EVERY
            code path in try/except so errors become printable warnings
            → False return (retry next iteration / next icon) instead of
            a crash.
          - ICONS ARE LAZY-LOADED / VIRTUALIZED: you cannot look them up
            at page-top and then jump to them because they don't exist in
            DOM until the user scrolls to their chapter. INSTEAD we do
            an INCREMENTAL scroll-sweep FIRST (0% → 15% → 30% → 45% →
            60% → 75% → 85%), collecting icons at every band, before we
            try to pick the "topmost" one.
          - Scroll is written to EVERY auto-detected scroll container
            (not only window.scrollTo), followed by wheel-deltas, then
            PageDown keys so the virtualized list populates.

        Then: pick topmost (lowest offsetTop) eligible icon, JUMP STRAIGHT
        to it, and click its clickable ancestor.
        """
        NEW_QUEST_SRC = "https://leap.acadally.com/student/static/icons/pe.svg"
        PAUSED_QUEST_SRC = "https://leap.acadally.com/student/static/icons/paused_icon.svg"
        COMPLETED_SRC = "https://leap.acadally.com/student/static/icons/completed_icon.svg"

        def _traceback_str(exc):
            # Return a compact 1-line traceback without huge stacks.
            try:
                import traceback
                lines = traceback.format_exception_only(type(exc), exc)
                return " | ".join([ln.strip() for ln in lines if ln.strip()])
            except Exception:
                return str(exc)

        def _expected_confirmation_is_visible(action):
            """Match only Acadally's selected quest confirmation button.
            This is based on its DOM label/classes, not URL, screen size, or
            viewport position, so another quest's CTA is never accepted.
            """
            try:
                return bool(self.driver.execute_script(
                    """
                    var wanted = arguments[0];
                    var required = [
                      'w-full', 'h-10', 'cursor-pointer', 'flex', 'items-center',
                      'justify-center', 'bg-[#ff8a00]', 'text-white', 'font-bold',
                      '!rounded-lg', 'border-[#CC7700]', 'border-b-[4px]',
                      'border-b-[#CC7700]', 'hover:bg-[#ff7300]',
                      'disabled:opacity-50', 'disabled:cursor-not-allowed',
                      'transition-colors', 'duration-200'
                    ];
                    var matches = Array.from(document.querySelectorAll('button')).filter(function(button) {
                      var label = (button.innerText || button.textContent || '').trim();
                      if (label !== wanted || button.disabled || !button.offsetParent) return false;
                      return required.every(function(name) { return button.classList.contains(name); });
                    });
                    return matches.length > 0;
                    """,
                    action,
                ))
            except Exception:
                return False

        try:
            self._pending_quest_action = None
            try:
                self.bring_browser_to_foreground()
            except Exception:
                pass
            time.sleep(0.3)

            viewport_h = max(
                int(self.driver.execute_script("return Math.max(window.innerHeight||0, 1);") or 1),
                1,
            )
            window_suspect_minimized = (viewport_h < 200)
            vh = viewport_h if not window_suspect_minimized else 600

            # =================================================================
            # 0) MULTI-CONTAINER SCROLL PRIMITIVE + AUTO-DETECT CONTAINERS.
            # =================================================================
            def _do_scroll_to(desired_y, label, timeout_extra=0):
                return self.driver.execute_async_script(
                    """
                    var desired = arguments[0];
                    var label = arguments[1];
                    var extra = arguments[2] || 0;
                    var done = arguments[arguments.length - 1];
                    setTimeout(function(){
                      try {
                        var list = [];
                        var questScroller = window.__acadallyQuestScroller;
                        if (questScroller && document.documentElement.contains(questScroller)) {
                          list.push({name:'quest-scroller', el: questScroller});
                        } else {
                          list.push({name:'window', el: window});
                        }
                        function readScrollMax() {
                          var m = 0;
                          try { m = Math.max(m, window.pageYOffset||0, window.scrollY||0); } catch(_) {}
                          for (var i=0; i<list.length; i++) {
                            try {
                              var s = list[i].el && list[i].el !== window ? (list[i].el.scrollTop||0) : 0;
                              if (s > m) m = s;
                            } catch(_) {}
                          }
                          return m;
                        }
                        var before = readScrollMax();
                        for (var attempt = 0; attempt < 3; attempt++) {
                          for (var i=0; i<list.length; i++) {
                            var L = list[i];
                            try {
                              if (L.el === window) {
                                try { window.scrollTo({top: desired, left: 0, behavior: 'auto'}); } catch(_) {}
                                try { window.scrollTo(0, desired); } catch(_) {}
                              } else {
                                try { if (L.el.scrollTo) L.el.scrollTo({top: desired, left: 0, behavior: 'auto'}); } catch(_) {}
                                try { L.el.scrollTop = desired; } catch(_) {}
                              }
                            } catch(_) {}
                          }
                          // wheel-deltas towards desired.
                          var cur = readScrollMax();
                          var dy = desired - cur;
                          if (Math.abs(dy) > 20) {
                            var steps = Math.min(50, Math.max(2, Math.ceil(Math.abs(dy) / 100)));
                            var per = dy > 0 ? 120 : -120;
                            for (var z=0; z<steps; z++) {
                              ['wheel','mousewheel','DOMMouseScroll'].forEach(function(t){
                                try {
                                  var ev;
                                  if (t==='DOMMouseScroll') {
                                    ev = document.createEvent('MouseEvents');
                                    ev.initMouseEvent(t, true, true, window, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
                                  } else {
                                    ev = new WheelEvent(t, {bubbles:true,cancelable:true,view:window,deltaY:per,deltaX:0,deltaMode:0,wheelDelta:-per*2});
                                  }
                                  try { window.dispatchEvent(ev); } catch(_) {}
                                  try { document.body.dispatchEvent(ev); } catch(_) {}
                                  try { if (list[0]) list[0].el.dispatchEvent(ev); } catch(_) {}
                                } catch(_) {}
                              });
                            }
                          }
                        }
                        // keyboard: up to 20x PageDown/PageUp if still far away.
                        for (var k=0; k<20; k++) {
                          var c = readScrollMax();
                          if (Math.abs(c - desired) < 80) break;
                          var kc = (desired - c) > 0 ? 'PageDown' : 'PageUp';
                          ['keydown','keypress','keyup'].forEach(function(t){
                            try {
                              var kc3 = kc==='PageDown'?34:33;
                              var ev = new KeyboardEvent(t, {key:kc,code:kc,keyCode:kc3,which:kc3,bubbles:true,cancelable:true,view:window});
                              try { (document.activeElement || document.body).dispatchEvent(ev); } catch(_) {}
                              try { document.body.dispatchEvent(ev); } catch(_) {}
                            } catch(_) {}
                          });
                          // accompany keyboard with equivalent scrollTop nudge.
                          var cur2 = readScrollMax();
                          var tgt2 = Math.max(0, cur2 + ((desired-cur2)>0 ? +700 : -700));
                          for (var i=0; i<list.length; i++) {
                            try {
                              if (list[i].el === window) continue;
                              list[i].el.scrollTop = tgt2;
                            } catch(_) {}
                          }
                        }
                        var after = readScrollMax();
                        done({before:before, after:after, moved:Math.abs(after-before)>10, desired:desired, delta:after-desired, label:label});
                      } catch (e) {
                        done({before:0, after:0, moved:false, desired:desired, delta:0, label:label, error: String(e && e.message ? e.message : e)});
                      }
                    }, 30 + extra);
                    """,
                    int(max(0, desired_y)),
                    str(label),
                    int(max(0, timeout_extra)),
                ) or {}

            # =================================================================
            # 1) INCREMENTAL SCROLL-SWEEP TO DISCOVER ICONS ACROSS CHAPTERS.
            #    (icons are virtualized / lazy - they pop into DOM only when
            #    their chapter is scrolled near the viewport.)
            # =================================================================
            # For every band we will:
            #   a) scroll there (using multi-container primitives)
            #   b) wait ~1.5s so React populates the chapter DOM
            #   c) snapshot <img> -> classify + store as (priority, offsetTop)
            BANDS = [0.0, 0.15, 0.30, 0.45, 0.60, 0.75, 0.90, 1.0]
            bands_done = 0
            seen_sigs = set()
            all_icons = []  # list of dicts {priority, offsetTop, img_index, src}

            # Identify the quest-list scroller.  Acadally keeps its chapters
            # in an inner overflow container, so document.body.scrollHeight
            # is often only one viewport high.
            total_h = max(
                int(self.driver.execute_script(
                    """
                    var candidates = [
                      document.scrollingElement,
                      document.documentElement,
                      document.body
                    ].filter(Boolean);
                    document.querySelectorAll('*').forEach(function(el) {
                      var style = getComputedStyle(el);
                      if (el.scrollHeight > el.clientHeight + 50 &&
                          /auto|scroll|overlay/.test(style.overflowY)) {
                        candidates.push(el);
                      }
                    });
                    candidates.sort(function(a, b) {
                      return (b.scrollHeight - b.clientHeight) -
                             (a.scrollHeight - a.clientHeight);
                    });
                    var scroller = candidates[0] || document.scrollingElement;
                    window.__acadallyQuestScroller = scroller;
                    return scroller.scrollHeight || 1;
                    """
                ) or 1),
                1,
            )
            print(f"   📏 Page totalH≈{total_h}px; scanning {len(BANDS)} scroll bands to discover lazy-loaded quest icons…")

            for band_idx, pct in enumerate(BANDS):
                target_y = int(total_h * pct)
                if not window_suspect_minimized:
                    # Bring band into middle of viewport (so icons populate).
                    target_y = max(0, target_y - vh // 2)
                # Scan through the actual end of the chapter list.
                cap = max(0, total_h - vh)
                target_y = min(target_y, cap)

                sc = _do_scroll_to(target_y, label=f"band {band_idx+1}/{len(BANDS)} @{int(pct*100)}%")
                moved = bool(sc.get("moved"))
                print(
                    f"      🎡 Pass {band_idx+1}/{len(BANDS)} [{int(pct*100)}%] → wanted y={target_y}, actual y={sc.get('after','?')} "
                    f"({'moved' if moved else 'NO-MOVE (maybe static page)'})"
                    + (f" err={sc.get('error')}" if sc.get("error") else "")
                )
                # Settle time for lazy-rendered quest cards to enter DOM.
                time.sleep(1.6)

                # Collect every <img> in DOM right now (this includes any
                # newly-populated icons from the chapter we just scrolled
                # into view).
                try:
                    snap = self.driver.execute_script(
                        """
                        var NEW_Q=arguments[0], PAUSE_Q=arguments[1], COMPL_Q=arguments[2];
                        var all = document.getElementsByTagName('img');
                        var res = [];
                        for (var i=0;i<all.length;i++) {
                          var img = all[i];
                          var src = (img && img.src) ? img.src : '';
                          if (!src) continue;
                          if (src.indexOf(COMPL_Q) !== -1 || /completed_icon\\.svg(\\?|#|$)/.test(src)) continue;
                          var prio = -1;
                          if (/paused_icon\\.svg(\\?|#|$)/.test(src) || src.indexOf(PAUSE_Q) !== -1) prio = 0;
                          else if (/pe\\.svg(\\?|#|$)/.test(src) || (src.indexOf(NEW_Q) !== -1)) prio = 1;
                          if (prio === -1) continue;
                          // absolute document Y via offsetTop walk.
                          var y = 0, n = img;
                          while (n) { y += (n.offsetTop || 0); n = n.offsetParent; }
                          // bbox in viewport coords.
                          var bt = -1, bw = 0, bh = 0;
                          try {
                            var r = img.getBoundingClientRect();
                            bt = r.top; bw = r.width; bh = r.height;
                          } catch(_) {}
                          res.push({priority: prio, offsetTop: y, img_index: i, src: src,
                                    bboxTop: bt, bboxW: bw, bboxH: bh});
                        }
                        return res;
                        """,
                        NEW_QUEST_SRC, PAUSED_QUEST_SRC, COMPLETED_SRC,
                    ) or []
                except Exception as ex:
                    print(f"      ⚠️  img snapshot failed ({_traceback_str(ex)}); skipping band {band_idx+1}")
                    continue

                added_in_band = 0
                for d in snap:
                    off = int(d.get("offsetTop") or 0)
                    sig = f"{d.get('src')}|{off}"
                    if sig in seen_sigs:
                        continue
                    seen_sigs.add(sig)
                    all_icons.append(d)
                    added_in_band += 1
                bands_done += 1
                print(f"      ➕ Found +{added_in_band} new eligible icons this band (total so far={len(all_icons)})")
                # Short-circuit sweep if we already have ≥1 paused quest
                # (paused is priority 0, we'd pick it anyway) OR ≥3 new.
                paused_count = sum(
                    1 for x in all_icons
                    if int(x.get("priority") if x.get("priority") is not None else 9) == 0
                )
                if paused_count >= 1 or len(all_icons) >= 3:
                    print(f"      ✂️  Early sweep stop ({paused_count} paused already visible)")
                    break

            # =================================================================
            # 2) PICK TOPMOST ELIGIBLE ICON (paused first).
            # =================================================================
            def _sort_key(ic):
                priority = ic.get("priority")
                return (
                    int(priority) if priority is not None else 99,
                    int(ic.get("offsetTop") or 10**12),
                )
            all_icons.sort(key=_sort_key)
            print(
                f"   🏁 Sweep finished: {bands_done} bands, {len(all_icons)} distinct eligible icons "
                f"(paused={sum(1 for x in all_icons if int(x.get('priority') if x.get('priority') is not None else 9)==0)}, new={sum(1 for x in all_icons if int(x.get('priority') if x.get('priority') is not None else 9)==1)})"
            )

            # This status is deliberately separate from the boolean return
            # value.  The batch loop must be able to distinguish:
            #   none       = there really is nothing left
            #   found_failed = a quest was found but its card could not be clicked
            #   clicked    = quest card was activated
            self._last_quest_click_status = "none"

            if not all_icons:
                print("   ℹ️  No pe.svg / paused_icon.svg icons anywhere. Falling back to CSS heuristics.")
                try:
                    fb_ok = bool(self._find_and_click_next_quest_card_fallback())
                    self._last_quest_click_status = "clicked" if fb_ok else "none"
                    return fb_ok
                except Exception as fx:
                    print(f"   ⚠️  Fallback finder crashed: {_traceback_str(fx)}")
                    self._last_quest_click_status = "none"
                    return False

            target = all_icons[0]
            tgt_offset = int(target.get("offsetTop") or 0)
            tgt_src = (target.get("src") or "").split("/")[-1]
            tgt_prio = int(target.get("priority") if target.get("priority") is not None else 1)
            expected_action = "Resume" if tgt_prio == 0 else "Start"
            print(f"   🎯 Selected {tgt_src} (priority={'paused' if tgt_prio==0 else 'new'}) @ y≈{tgt_offset}px")

            # =================================================================
            # 3) DEFINITIVE JUMP TO SELECTED ICON.
            # =================================================================
            desired_jump = max(0, tgt_offset - vh // 2)
            desired_jump = min(desired_jump, max(0, total_h - vh))
            jump_res = _do_scroll_to(desired_jump, label=f"jump → {tgt_src}", timeout_extra=120)
            print(
                f"      🛬 Jump: wanted {desired_jump}, got y={jump_res.get('after','?')}, "
                f"moved={'YES' if jump_res.get('moved') else 'NO'}"
                + (f"  err={jump_res.get('error')}" if jump_res.get("error") else "")
            )
            time.sleep(1.2)

            # =================================================================
            # 4) RE-FIND THE CURRENT DOM ELEMENT AFTER SCROLLING.
            #
            # IMPORTANT: the old code saved document.getElementsByTagName('img')
            # index during discovery and reused that index later. React/lazy
            # rendering can insert/remove <img> nodes between those two moments,
            # especially on slower laptops. That makes index 53 become some
            # unrelated <span>/<img> chain and the click silently does nothing.
            #
            # We therefore identify the quest by its stable icon source + nearby
            # document Y and obtain a FRESH WebElement immediately before click.
            # =================================================================
            def _get_fresh_quest_element(target_y, target_priority, preferred_src):
                return self.driver.execute_script(
                    """
                    var targetY = arguments[0];
                    var targetPriority = arguments[1];
                    var preferred = arguments[2] || '';
                    var imgs = Array.from(document.getElementsByTagName('img'));
                    var bestImg = null;
                    var bestScore = Infinity;

                    function docY(img) {
                      var y = 0, n = img;
                      while (n) { y += (n.offsetTop || 0); n = n.offsetParent; }
                      return y;
                    }
                    function eligible(img) {
                      var s = (img && img.src) ? img.src : '';
                      if (!s) return false;
                      if (/completed_icon\\.svg(\\?|#|$)/i.test(s)) return false;
                      if (targetPriority === 0)
                        return /paused_icon\\.svg(\\?|#|$)/i.test(s) || s.indexOf('paused_icon.svg') !== -1;
                      return /pe\\.svg(\\?|#|$)/i.test(s) || s.indexOf('/pe.svg') !== -1;
                    }

                    for (var i=0; i<imgs.length; i++) {
                      var img = imgs[i];
                      if (!eligible(img)) continue;
                      var s = img.src || '';
                      var y = docY(img);
                      var r = null;
                      try { r = img.getBoundingClientRect(); } catch(_) {}
                      var visiblePenalty = 0;
                      if (r && (r.width <= 0 || r.height <= 0)) visiblePenalty = 100000;
                      var srcPenalty = preferred && s.indexOf(preferred) !== -1 ? 0 : 5000;
                      var score = Math.abs(y - targetY) + srcPenalty + visiblePenalty;
                      if (score < bestScore) {
                        bestScore = score;
                        bestImg = img;
                      }
                    }
                    if (!bestImg) return null;

                    // Find the actual clickable card, not an arbitrary inner span.
                    var chain = [];
                    var n = bestImg;
                    for (var k=0; k<15 && n; k++, n=n.parentElement) chain.push(n);

                    function textOf(el) {
                      try { return ((el.innerText || el.textContent || '') + '').trim().toLowerCase(); }
                      catch(_) { return ''; }
                    }
                    function clsOf(el) {
                      try { return ((el.className || '') + '').toLowerCase(); }
                      catch(_) { return ''; }
                    }
                    function hasReactClick(el) {
                      // React stores event props on DOM nodes under a private
                      // property such as __reactProps$xxxx.  Looking for an
                      // actual onClick handler is much more reliable than
                      // guessing from Tailwind class names.
                      try {
                        var keys = Object.keys(el);
                        for (var z=0; z<keys.length; z++) {
                          if (keys[z].indexOf('__reactProps$') === 0) {
                            var props = el[keys[z]];
                            if (props && (typeof props.onClick === 'function' ||
                                          typeof props.onMouseDown === 'function' ||
                                          typeof props.onPointerDown === 'function')) {
                              return true;
                            }
                          }
                        }
                      } catch(_) {}
                      return false;
                    }

                    function scoreClickable(el, depth) {
                      if (!el || !el.tagName) return -999999;
                      var tag = el.tagName.toLowerCase();
                      var cls = clsOf(el);
                      var role = '';
                      try { role = (el.getAttribute('role') || '').toLowerCase(); } catch(_) {}
                      var href = '';
                      try { href = el.getAttribute('href') || ''; } catch(_) {}
                      var aria = '';
                      try { aria = (el.getAttribute('aria-label') || '').toLowerCase(); } catch(_) {}
                      var s = -500;

                      // FIRST PRIORITY: the actual React event owner.
                      if (hasReactClick(el)) s += 5000;

                      // Real HTML interaction.
                      if (tag === 'button') s += 3000;
                      if (tag === 'a') s += 2800;
                      if (role === 'button') s += 2600;
                      if (href) s += 1800;
                      if (el.onclick || el.getAttribute('onclick')) s += 1600;
                      if (el.tabIndex >= 0) s += 500;

                      // CSS cursor:pointer is another strong signal that this
                      // element is the intended click surface.
                      try {
                        if (getComputedStyle(el).cursor === 'pointer') s += 1800;
                      } catch(_) {}

                      // Card-like names help break ties, but NEVER by themselves
                      // enough to select a full-page layout wrapper.
                      if (/quest|quiz|challenge|assignment/.test(cls)) s += 900;
                      if (/card|tile|row|item|cell|chapter|clickable/.test(cls)) s += 700;
                      if (/start|resume|attempt|begin|play/.test(cls + ' ' + aria)) s += 400;

                      // The image/span itself should only win when it really is
                      // interactive.
                      if (tag === 'img' || tag === 'span') s -= 1000;

                      // Strongly reject page/layout wrappers.
                      try {
                        var rr = el.getBoundingClientRect();
                        if (rr.width > innerWidth * 0.95 || rr.height > innerHeight * 0.95) s -= 5000;
                        if (rr.width > innerWidth * 0.80 && rr.height > innerHeight * 0.60) s -= 2500;
                      } catch(_) {}

                      // Nearest genuine click owner wins ties.
                      s -= depth * 15;
                      return s;
                    }

                    var best = bestImg;
                    var bestScore2 = scoreClickable(bestImg, 0);
                    for (var j=1; j<chain.length; j++) {
                      var candidate = chain[j];
                      var cs = scoreClickable(candidate, j);
                      if (cs > bestScore2) {
                        bestScore2 = cs;
                        best = candidate;
                      }
                    }

                    // If no real interactive/card ancestor was found, do NOT
                    // climb to a random layout <div>.  The icon's own hit point
                    // is a much safer fallback.
                    if (best === bestImg || best.tagName.toLowerCase() === 'span' || bestScore2 < 1000) {
                      best = bestImg;
                    }

                    try { best.scrollIntoView({behavior:'auto', block:'center', inline:'center'}); } catch(_) {}
                    return best;
                    """,
                    int(target_y),
                    int(target_priority),
                    preferred_src,
                )

            def _click_fresh_quest(target_y, target_priority, preferred_src, attempt_label):
                """Get a fresh quest-card element and click it using several
                independent input paths. Returns a small result dictionary."""
                result = {"ok": False, "tag": "?", "cls": "", "method": attempt_label}
                try:
                    elem = _get_fresh_quest_element(target_y, target_priority, preferred_src)
                    if elem is None:
                        result["reason"] = "fresh quest element not found"
                        return result

                    try:
                        result["tag"] = (elem.tag_name or "?").lower()
                    except Exception:
                        pass
                    try:
                        result["cls"] = (elem.get_attribute("class") or "")[:100]
                    except Exception:
                        pass

                    # Fresh native Selenium click first. This is important on
                    # machines where React ignores a synthetic JS-only click.
                    try:
                        self.bring_browser_to_foreground()
                    except Exception:
                        pass
                    try:
                        WebDriverWait(self.driver, 5).until(lambda d: elem.is_displayed() and elem.is_enabled())
                    except Exception:
                        pass

                    try:
                        ActionChains(self.driver).move_to_element(elem).pause(0.15).click().perform()
                        result["ok"] = True
                        result["method"] = attempt_label + ":ActionChains"
                        return result
                    except Exception:
                        pass

                    try:
                        elem.click()
                        result["ok"] = True
                        result["method"] = attempt_label + ":WebElement.click"
                        return result
                    except Exception:
                        pass

                    # JS .click() is kept only as a fallback after the native
                    # click paths, not as the primary mechanism.
                    try:
                        self.driver.execute_script("arguments[0].click();", elem)
                        result["ok"] = True
                        result["method"] = attempt_label + ":JS-click"
                        return result
                    except Exception:
                        pass
                except Exception as ex:
                    result["reason"] = _traceback_str(ex)
                return result

            # Re-find immediately before clicking. Do it more than once if the
            # page is still re-rendering, which is common on slower laptops.
            click_result = None
            for click_try in range(1, 4):
                click_result = _click_fresh_quest(
                    tgt_offset,
                    tgt_prio,
                    "paused_icon.svg" if tgt_prio == 0 else "pe.svg",
                    f"try-{click_try}",
                )
                print(
                    f"   🖱️  Quest-card click {click_try}/3 → <{click_result.get('tag','?')}> "
                    f"({str(click_result.get('cls',''))[:60]}) via {click_result.get('method','?')}"
                )
                time.sleep(1.2)

                # A card click is accepted only when the exact Start/Resume
                # confirmation for THIS selected quest exists.  URL changes or
                # generic CTAs elsewhere on the Journey page are not evidence.
                if _expected_confirmation_is_visible(expected_action):
                    self._pending_quest_action = expected_action
                    print(f"   ✅ Quest click CONFIRMED ({expected_action} confirmation is ready)")
                    self._last_quest_click_status = "clicked"
                    return True

                if click_try < 3:
                    print("   🔁 No state change yet; re-finding the quest in the fresh DOM and retrying...")
                    time.sleep(0.8)

            # =================================================================
            # 5) LAST RESORT: use the other discovered quests, but ALWAYS
            #    re-find them by source + Y. Never reuse their old DOM index.
            # =================================================================
            print("   ⚠️  Primary quest-card click had no visible effect; trying fallback icons...")
            for fb_idx, fb in enumerate(all_icons[1:3], start=1):
                fb_off = int(fb.get("offsetTop") or 0)
                fb_prio = int(fb.get("priority") if fb.get("priority") is not None else 1)
                fb_src = "paused_icon.svg" if fb_prio == 0 else "pe.svg"
                fb_label = (fb.get("src") or "").split("/")[-1]
                print(f"   🔁 Fallback #{fb_idx}: {fb_label} near y={fb_off}")
                try:
                    _do_scroll_to(max(0, fb_off - vh // 2), label=f"fallback-jump-{fb_idx}")
                    time.sleep(1.0)
                except Exception:
                    pass

                for retry in range(1, 3):
                    try:
                        fb_result = _click_fresh_quest(fb_off, fb_prio, fb_src, f"fallback-{fb_idx}-{retry}")
                        print(
                            f"      🖱️  Fallback click {retry}/2 → <{fb_result.get('tag','?')}> "
                            f"({str(fb_result.get('cls',''))[:60]}) via {fb_result.get('method','?')}"
                        )
                    except Exception as fx:
                        print(f"      ⚠️  fallback {fb_idx} click failed: {_traceback_str(fx)}")
                    time.sleep(1.2)
                    fb_action = "Resume" if fb_prio == 0 else "Start"
                    if _expected_confirmation_is_visible(fb_action):
                        self._pending_quest_action = fb_action
                        print(f"   ✅ Fallback quest click CONFIRMED ({fb_action} confirmation is ready)")
                        self._last_quest_click_status = "clicked"
                        return True

            print("   ❌ Could not get any quest card to respond to a click this iteration.")
            self._last_quest_click_status = "found_failed"
            return False
        except Exception as big_ex:
            print(f"   💥 EXCEPTION inside find_and_click_next_quest_card: {_traceback_str(big_ex)}")
            self._last_quest_click_status = "found_failed" if all_icons else "none"
            return False

    def _find_and_click_next_quest_card_fallback(self):
        """Legacy CSS-heuristic quest finder used ONLY if the image-src
        matcher finds zero eligible icons. Same logic as before, preserved
        for robustness on different page layouts.
        """
        card_css = [
            "a[class*='quest'], a[class*='quiz'], a[class*='challenge'], a[class*='assignment']",
            "div[class*='quest-card'], div[class*='quiz-card'], div[class*='card-quiz']",
            "[class*='cards'] > [class*='card']",
            "section[class*='quests'] [class*='card']",
            "main [class*='list'] > [class*='item']",
            "div[role='list'] > div[role='listitem']",
        ]
        cards = []
        seen = set()
        for css in card_css:
            try:
                for c in self.driver.find_elements(By.CSS_SELECTOR, css):
                    if not c.is_displayed():
                        continue
                    try:
                        k = c.get_attribute("outerHTML")[:200]
                    except Exception:
                        k = ""
                    if k and k in seen:
                        continue
                    seen.add(k)
                    cards.append(c)
            except Exception:
                pass
        if not cards:
            print("   ℹ️  No quest cards found via fallback CSS selectors either.")
            return False

        def card_score(el):
            txt = ""
            cls = ""
            try:
                txt = (el.text or "").lower()
            except Exception:
                txt = ""
            try:
                cls = (el.get_attribute("class") or "").lower()
            except Exception:
                cls = ""
            if ("completed" in txt) or ("finished" in txt) or ("done" in txt) or ("trophy" in txt) or ("100%" in txt):
                return -1
            if ("completed" in cls) or ("done" in cls) or ("locked" in cls):
                return -1
            score = 0
            if ("start" in txt) or ("resume" in txt) or ("attempt" in txt) or ("play" in txt) or ("begin" in txt):
                score += 3
            if ("in progress" in txt) or ("progress" in cls and "0%" not in txt):
                score += 2
            if ("not attempted" in txt) or ("not started" in txt):
                score += 2
            return score

        scored = [(card_score(c), c) for c in cards]
        scored.sort(key=lambda x: x[0], reverse=True)
        top_score, top_card = scored[0]
        if top_score < 0:
            print("   ✅ All quest cards appear completed/locked. Nothing left to run.")
            return False

        cta_css_list = [
            "button:has-text('Start')",
            "button:has-text('Resume')",
            "button:has-text('Attempt')",
            "button:has-text('Begin')",
            "a:has-text('Start')",
            "a:has-text('Resume')",
            "a[class*='start']",
            "a[class*='resume']",
            "button:nth-of-type(1)",
            "a[role='button']",
        ]
        clicked = False
        for css in cta_css_list:
            try:
                for el in top_card.find_elements(By.CSS_SELECTOR, css):
                    if el.is_displayed() and el.is_enabled():
                        self.driver.execute_script("arguments[0].click();", el)
                        print(f"   🎯 Clicked quest CTA (fallback) via CSS: {css}")
                        clicked = True
                        break
            except Exception:
                pass
            if clicked:
                break
        if not clicked:
            try:
                self.driver.execute_script("arguments[0].click();", top_card)
                print("   🎯 Clicked quest card directly (fallback)")
                clicked = True
            except Exception:
                pass
        if clicked:
            time.sleep(3)
        return clicked

    def handle_start_or_resume_popup(self, timeout_s=15):
        """Click only the exact confirmation action for the card just opened.

        The expected label is set by find_and_click_next_quest_card(): a new
        card may only click Start; a paused card may only click Resume.
        No page-wide Start/Resume scan is performed. If the page contains
        more than one matching control, the one in the active confirmation
        layer is preferred without relying on screen dimensions.
        """
        expected = getattr(self, "_pending_quest_action", None)
        if expected not in ("Start", "Resume"):
            print("   ⚠️  No selected-quest confirmation action was recorded.")
            return False

        required_classes = [
            "w-full", "h-10", "cursor-pointer", "flex", "items-center",
            "justify-center", "bg-[#ff8a00]", "text-white", "font-bold",
            "!rounded-lg", "border-[#CC7700]", "border-b-[4px]",
            "border-b-[#CC7700]", "hover:bg-[#ff7300]",
            "disabled:opacity-50", "disabled:cursor-not-allowed",
            "transition-colors", "duration-200",
        ]
        print(f"   🛎️  Clicking selected quest confirmation: {expected}")
        end_at = time.time() + timeout_s
        while time.time() < end_at:
            try:
                clicked = self.driver.execute_script(
                    """
                    var wanted = arguments[0], required = arguments[1];
                    function usable(button) {
                      if (button.disabled || !button.offsetParent) return false;
                      var label = (button.innerText || button.textContent || '').trim();
                      if (label !== wanted) return false;
                      return required.every(function(name) { return button.classList.contains(name); });
                    }
                    function confirmationRank(button) {
                      var rank = 0, node = button;
                      for (var i = 0; i < 12 && node; i++, node = node.parentElement) {
                        var cls = (node.className || '').toString().toLowerCase();
                        var style = getComputedStyle(node);
                        if (node.getAttribute('role') === 'dialog' ||
                            node.getAttribute('aria-modal') === 'true' ||
                            /modal|popup|dialog|confirm|overlay/.test(cls)) rank += 10000;
                        if (style.position === 'fixed') rank += 5000;
                        var z = parseInt(style.zIndex, 10);
                        if (!isNaN(z)) rank += Math.min(z, 1000);
                      }
                      return rank;
                    }
                    var buttons = Array.from(document.querySelectorAll('button')).filter(usable);
                    if (!buttons.length) return {ok:false, count:0};
                    buttons.sort(function(a, b) {
                      return confirmationRank(b) - confirmationRank(a) ||
                             Array.from(document.querySelectorAll('button')).indexOf(b) -
                             Array.from(document.querySelectorAll('button')).indexOf(a);
                    });
                    var button = buttons[0];
                    button.click();
                    return {ok:true, label:(button.innerText || button.textContent || '').trim(), count:buttons.length};
                    """,
                    expected,
                    required_classes,
                ) or {}
            except Exception:
                clicked = {}
            if clicked.get("ok"):
                self._pending_quest_action = None
                print(f"   ▶️  Clicked selected quest confirmation: {clicked.get('label')}")
                time.sleep(1.0)
                return True
            time.sleep(0.25)
        print(f"   ⚠️  Could not identify the {expected} confirmation button yet; keeping the current quest open and retrying.")
        return False

    def wait_until_on_first_question(self, timeout_s=25):
        """Return True once we appear to actually be inside a running
        quiz (options A/B/C/D or radio inputs are visible). Used by the
        All-Quizzes path after a new quest is launched so we don't start
        screenshotting the quest list page by accident.
        """
        end_at = time.time() + timeout_s
        while time.time() < end_at:
            try:
                options = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "input[type='radio'], input[type='checkbox'], "
                    "[class*='option'], [class*='choice'], [class*='answer-option']"
                )
            except Exception:
                options = []
            visible_options = 0
            for o in options:
                try:
                    if o.is_displayed():
                        visible_options += 1
                except Exception:
                    pass
            if visible_options >= 2:
                return True
            # Also accept presence of a "Next" nav button as quiz-started
            try:
                if self.driver.find_elements(By.CSS_SELECTOR,
                    "button[class*='next'], [class*='next-btn'], button[class*='submit']"
                ):
                    return True
            except Exception:
                pass
            time.sleep(0.75)
        return False

    def run_single_quiz_then_handle_submit_confirm(self):
        """Wrapper used in ALL-QUIZZES mode. It runs the existing
        run_quiz_automation verbatim, then immediately handles the
        post-submit confirmation popup and returns to the quest list
        page, all via CSS selectors only.

        The existing run_quiz_automation() method itself is NOT edited.
        """
        # 1) Use the original quiz loop - no behavior changes inside it.
        self.run_quiz_automation()
        # 2) The existing quiz loop clicked the first Submit button. Keep
        # waiting on that same post-submit popup until its positive action is
        # clicked; do not move back through browser history.
        while not self.confirm_submit_popup():
            print("⚠️  Submit confirmation cannot be identified yet; retrying the current quiz.")
            time.sleep(1.0)
        # 3) Acadally may show Continue first, or Go to Journey directly.
        # Stay on this completion flow until Go to Journey is clicked.
        while not self.wait_for_results_page_and_go_back():
            print("⚠️  Go to Journey is not visible yet; waiting on the completion flow.")
            time.sleep(1.0)
        return True

    def run_quiz_automation(self):
        """Main quiz automation loop"""
        try:
            print("\n🚀 Starting quiz automation...")
            
            question_count = 0
            max_questions = 30  # Safety limit
            
            while question_count < max_questions:
                question_count += 1
                print(f"\n{'='*40}")
                print(f"📝 QUESTION {question_count}")
                print(f"{'='*40}")
                
                # Handle scrolling
                self.handle_scrolling()
                
                # Check if quiz ended
                if self.check_if_quiz_ended():
                    print("🎉 Quiz completed successfully!")
                    break
                
                # Take in-memory-only screenshot (no files written to disk)
                screenshot_bytes = self.take_question_screenshot()
                
                if not screenshot_bytes:
                    print("❌ Failed to take screenshot")
                    break
                
                # Get AI answer via multimodal API
                correct_option = self.get_ai_answer_from_screenshot(screenshot_bytes)
                
                if correct_option is None:
                    print("\n❌ Could not extract valid A/B/C/D answer from AI response")
                    print("❌ Stopping on this question. Please answer manually to continue.")
                    input("\nPress Enter after manually answering this question to continue...")
                    print("➡️ Attempting to navigate to next question after manual answer...")
                    result = self.navigate_to_next()
                    if result == "submit":
                        print("🎉 Quiz submitted successfully!")
                        break
                    elif result == "next":
                        print("⏳ Waiting for next question to load...")
                        time.sleep(4)
                        continue
                    else:
                        print("❌ Could not navigate. Manual intervention needed.")
                        break
                
                print(f"🎯 Final decision: Option {correct_option} (Letter {chr(64 + correct_option)})")
                
                # Select answer with visual feedback check
                if self.select_answer_with_visual_feedback(correct_option):
                    print("✅ Answer selection attempted")
                else:
                    print("⚠️ Failed to select answer")
                
                time.sleep(1.5)  # Give UI time to update
                
                # Navigate to next question
                print("➡️ Navigating to next question...")
                result = self.navigate_to_next()
                
                if result == "submit":
                    print("🎉 Quiz submitted successfully!")
                    break
                elif result == "unknown":
                    print("🤔 Could not find navigation button. Checking if quiz ended...")
                    if self.check_if_quiz_ended():
                        print("🎉 Quiz completed!")
                        break
                    else:
                        print("❌ Stuck on question. Manual intervention needed.")
                        break
                
                # Wait for next question to load
                print("⏳ Waiting for next question to load...")
                time.sleep(4)
                
            print(f"\n✅ Completed {question_count} questions")
            
        except Exception as e:
            print(f"❌ Error in quiz automation: {e}")
        finally:
            print("\n📊 Bot session ended. You can close the browser manually.")

# Configuration - ADD YOUR NVIDIA API KEY HERE
# Get a key from https://build.nvidia.com/
# Important - ADD API KEY OR IT WON'T WORK
# ADD IT HERE ⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️
NVIDIA_API_KEY = ""

def prompt_mode():
    """First-run mandatory choice: single quiz, or all available quizzes.
    Validates input and returns "1" or "2".
    """
    print("\n" + "=" * 50)
    print("  Select run mode")
    print("")
    print("  [1] Do One Quiz Only (original behavior preserved)")
    print("  [2] Complete All Available Quizzes (automatic batch)")
    print("=" * 50)
    choice = None
    while choice not in ("1", "2"):
        choice = input("Enter 1 or 2: ").strip()
        if choice not in ("1", "2"):
            print("Invalid input. Please enter 1 or 2.")
    return choice

def run_one_quiz_loop_original(bot):
    """Preserves the original main() flow 100% unchanged:
    user navigates to quiz manually, script runs it, then the
    post-quiz [1] Start another quiz / [2] Exit menu is shown.
    Browser stays open until the user presses Enter at the end.
    """
    # Identical to the previous main() behavior.
    while True:
        # Wait for user to login and start quiz
        bot.wait_for_user_ready()

        # Start automation
        bot.run_quiz_automation()

        # Post-quiz: explicit choice between starting another quiz or exiting
        print("\n" + "=" * 50)
        print("  Quiz finished. What would you like to do?")
        print("")
        print("  [1] Start another quiz")
        print("  [2] Exit the application")
        print("=" * 50)

        choice = None
        while choice not in ("1", "2"):
            choice = input("Enter 1 or 2: ").strip()
            if choice not in ("1", "2"):
                print("Invalid input. Please enter 1 or 2.")

        if choice == "2":
            print("Exiting application.")
            break
        else:
            print("\nPlease navigate to the new quiz and get to the first question...")

    # Keep browser open until user confirms.
    input("\nPress Enter to close this window...")

def run_all_quizzes_loop(bot):
    """Batch mode: complete every startable quiz without the user
    manually navigating between quizzes.

    Flow:
      1. User logs in and navigates to the quest selector page (the
         page whose UI matches quest.png in the project folder).
      2. Script finds the most-startable quest card via CSS selectors.
      3. Handles Start/Resume confirmation popup.
      4. Runs existing quiz automation.
      5. Handles Submit confirmation popup.
      6. Returns to quest list.
      7. Repeats until no startable quests remain.
      8. Closes the browser and exits cleanly.
    """
    # Initial one-time user readiness check on the quest-list page.
    print("\n" + "=" * 50)
    print("  ALL-QUIZZES MODE")
    print("=" * 50)
    print("Please manually:")
    print("1. Login to your account (if not already logged in)")
    print("2. Navigate to the QUEST SELECTOR page (quest.png)")
    print("3. You do NOT need to open any individual quiz")
    print("4. Come back here and press Enter to begin the batch.")
    print("=" * 50)
    input("Press Enter when you're on the quest selector page...")

    # Critical: even if user minimized Chrome before pressing Enter,
    # bring it back to front, restore it, and spoof visibility state.
    # Without this, is_displayed() / bbox / scrollIntoView all fail.
    print("   🪟 Bringing Chrome window to front (restore minimized if needed)...")
    bot.bring_browser_to_foreground()
    time.sleep(1.2)

    quizzes_run = 0
    max_quizzes_safety = 50  # hard cap to prevent accidental infinite loops

    while quizzes_run < max_quizzes_safety:
        print("\n" + "🔄" * 20)
        print(f"📦 Looking for the next quiz to start (already ran: {quizzes_run})")

        # 1) Find and click a startable quest card on the list page.
        clicked_card = bot.find_and_click_next_quest_card()
        if not clicked_card:
            click_status = getattr(bot, "_last_quest_click_status", "none")
            if click_status == "found_failed":
                print("⚠️  A startable quest was found, but the click did not register. Retrying instead of ending the batch...")
                time.sleep(1.5)
                continue
            print("✅✅ No more startable quests found. Batch complete!")
            break

        # 2) Handle the "Start" / "Resume" confirmation menu.
        while not bot.handle_start_or_resume_popup():
            # Keep waiting on this selected quest only. Never resume the
            # quest scan or close Chrome because its confirmation is late.
            print("⚠️  Quest confirmation cannot be identified yet; retrying the same quest...")
            time.sleep(1.0)

        # 3) Wait until we're really inside the quiz so the screenshot
        #    logic doesn't grab the quest list page by mistake.
        if not bot.wait_until_on_first_question():
            print("⚠️  Could not confirm quiz started. Will try the next card.")
            # Try to bounce back to the list for the next iteration.
            bot.wait_for_results_page_and_go_back()
            continue

        quizzes_run += 1
        print(f"\n▶️  QUIZ #{quizzes_run} BEGINNING")
        print("▶️" * 30)

        # 4) Run the quiz + handle the submit confirm popup + return
        #    to the quest selector page. Internally this calls the
        #    existing unmodified run_quiz_automation() verbatim.
        bot.run_single_quiz_then_handle_submit_confirm()

        print(f"✅ QUIZ #{quizzes_run} FINISHED")

    # End of batch: close the driver and exit without asking the user.
    try:
        if bot.driver is not None:
            print("🚪 Closing browser...")
            bot.driver.quit()
    except Exception as e:
        print(f"⚠️  Error closing browser: {e}")
    print("\n🎉 All-Quizzes batch run finished. Exiting.")

def main():
    print("🚀 ACADALLY QUIZ BOT (NVIDIA NIM)")
    print("=" * 50)

    mode = prompt_mode()
    print(f"ℹ️  Selected mode: {'[1] One Quiz Only' if mode == '1' else '[2] Complete All Quizzes'}")

    # Initialize bot
    bot = AcadallyBot(NVIDIA_API_KEY)

    # Setup driver and open Acadally
    print("🌐 Launching browser and opening Acadally...")
    if not bot.setup_driver():
        print("❌ Failed to setup browser")
        return

    try:
        if mode == "1":
            # 100% original single-quiz flow: unchanged menus, browser
            # stays open at the end until user presses Enter.
            run_one_quiz_loop_original(bot)
        else:
            # Batch mode: auto-navigate between quizzes, auto-close
            # browser at the end.
            run_all_quizzes_loop(bot)
    except KeyboardInterrupt:
        print("\n🛑 User interrupted via Ctrl+C. Exiting.")
    finally:
        # In single-quiz mode bot.driver is intentionally left open so
        # the user can inspect it; in all-quizzes mode it is already
        # closed above. A no-op quit() attempt is harmless either way.
        try:
            if mode == "2" and bot.driver is not None:
                bot.driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
