"""
AcadAlly Automizer
Created by: Shreyansh Gupta (AeroZer0Grinder)
Discord: aerozer0grinder
"""
import time
import base64
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import json


class AcadallyBot:
    def __init__(self, openrouter_api_key):
        self.openrouter_api_key = openrouter_api_key
        self.driver = None
        
    def setup_driver(self):
        """Setup Chrome driver and open Acadally"""
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--start-maximized")
        
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
        """Take screenshot of the current question area"""
        try:
            screenshot = self.driver.get_screenshot_as_png()
            screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')
            return screenshot_b64
        except Exception as e:
            print(f"Error taking screenshot: {e}")
            return None
    
    def extract_visible_text(self):
        """Extract visible text from the current page"""
        try:
            visible_text = self.driver.find_element(By.TAG_NAME, "body").text
            return visible_text
        except Exception as e:
            print(f"Error extracting text: {e}")
            return ""
    
    def get_ai_answer_from_screenshot(self, screenshot_b64, visible_text):
        """Use OpenRouter API with screenshot and text context"""
        try:
            # Display full text and screenshot info
            print(f"📄 FULL QUESTION TEXT ({len(visible_text)} characters):")
            print("="*50)
            print(visible_text)
            print("="*50)
            print(f"📸 Screenshot captured ({len(screenshot_b64)} bytes)")
            
            # Prepare the prompt with FULL text content
            prompt = f"""
            Analyze this academic quiz question and choose the correct answer from the options.

            FULL QUESTION CONTENT:
            {visible_text}

            Instructions:
            1. Read the entire question carefully
            2. Identify all available options (usually 2-4 options)
            3. Choose the correct answer based on academic knowledge
            4. Return ONLY the option number (1, 2, 3, or 4)

            Format your response as exactly: ANSWER: [number]
            Example: ANSWER: 2

            If you're unsure, make an educated guess based on the question content.
            """
            
            headers = {
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "deepseek/deepseek-chat",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": 150
            }
            
            print("🤖 Sending to AI for analysis...")
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                answer_text = result['choices'][0]['message']['content'].strip()
                print(f"🤖 AI Raw Response: {answer_text}")
                
                # Extract the answer number
                import re
                match = re.search(r'ANSWER:\s*(\d+)', answer_text, re.IGNORECASE)
                if match:
                    answer_num = int(match.group(1))
                    print(f"✅ Extracted answer: Option {answer_num}")
                    return answer_num
                else:
                    # Look for standalone numbers
                    numbers = re.findall(r'\b([1-4])\b', answer_text)
                    if numbers:
                        answer_num = int(numbers[0])
                        print(f"✅ Found number in response: Option {answer_num}")
                        return answer_num
                    
            print("❌ Could not extract answer, using option 1")
            return 1
            
        except Exception as e:
            print(f"❌ Error getting AI answer: {e}")
            return 1
    
    def select_answer(self, option_number):
        """Select the answer option"""
        try:
            print(f"🎯 Attempting to select option {option_number}")
            
            # Try different selection strategies
            strategies = [
                self._click_by_css_selector,
                self._click_by_xpath,
                self._click_by_text_content,
                self._click_radio_buttons
            ]
            
            for strategy in strategies:
                if strategy(option_number):
                    return True
            
            return False
            
        except Exception as e:
            print(f"Error selecting answer: {e}")
            return False
    
    def _click_by_css_selector(self, option_number):
        """Try clicking by CSS selectors"""
        selectors = [
            f"[class*='option']:nth-of-type({option_number})",
            f"[class*='choice']:nth-of-type({option_number})",
            f".answer-option:nth-of-type({option_number})",
            f"div[class*='option']:nth-child({option_number})",
            f"li:nth-child({option_number})",
            f"[data-option='{option_number}']",
            f"[data-index='{option_number-1}']"
        ]
        
        for selector in selectors:
            try:
                element = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                self.driver.execute_script("arguments[0].click();", element)
                print(f"✅ Clicked using CSS: {selector}")
                return True
            except:
                continue
        return False
    
    def _click_by_xpath(self, option_number):
        """Try clicking by XPath"""
        xpaths = [
            f"(//*[contains(@class, 'option')])[{option_number}]",
            f"(//*[contains(@class, 'choice')])[{option_number}]",
            f"(//*[contains(text(), 'Option {option_number}')])[1]",
            f"(//label[contains(., 'Option {option_number}')])[1]",
            f"(//div[contains(@class, 'answer')])[{option_number}]",
            f"(//*[@role='radio'])[{option_number}]",
            f"(//input[@type='radio']/following-sibling::label)[{option_number}]"
        ]
        
        for xpath in xpaths:
            try:
                element = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                self.driver.execute_script("arguments[0].click();", element)
                print(f"✅ Clicked using XPath: {xpath}")
                return True
            except:
                continue
        return False
    
    def _click_by_text_content(self, option_number):
        """Try clicking by text content"""
        try:
            # Get all clickable elements that might be options
            possible_elements = self.driver.find_elements(By.CSS_SELECTOR, 
                "[class*='option'], [class*='choice'], .answer-option, li, label, div[role='button'], .answer-choice")
            
            if option_number <= len(possible_elements):
                element = possible_elements[option_number-1]
                self.driver.execute_script("arguments[0].click();", element)
                print(f"✅ Clicked element at position {option_number}")
                return True
        except Exception as e:
            print(f"Text content click failed: {e}")
        return False
    
    def _click_radio_buttons(self, option_number):
        """Try clicking radio buttons or checkboxes"""
        try:
            radio_buttons = self.driver.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
            if option_number <= len(radio_buttons):
                radio = radio_buttons[option_number-1]
                radio_id = radio.get_attribute('id')
                if radio_id:
                    try:
                        label = self.driver.find_element(By.CSS_SELECTOR, f"label[for='{radio_id}']")
                        self.driver.execute_script("arguments[0].click();", label)
                    except:
                        self.driver.execute_script("arguments[0].click();", radio)
                else:
                    self.driver.execute_script("arguments[0].click();", radio)
                print(f"✅ Clicked radio button {option_number}")
                return True
        except Exception as e:
            print(f"Radio button click failed: {e}")
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
            # Scroll down and up to load all content
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
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
                
                # Take screenshot and extract text
                screenshot_b64 = self.take_question_screenshot()
                visible_text = self.extract_visible_text()
                
                if not screenshot_b64:
                    print("❌ Failed to take screenshot")
                    break
                
                # Get AI answer
                correct_option = self.get_ai_answer_from_screenshot(screenshot_b64, visible_text)
                print(f"🎯 Final decision: Option {correct_option}")
                
                # Select answer
                if self.select_answer(correct_option):
                    print("✅ Answer selected successfully")
                else:
                    print("⚠️ Failed to select answer, trying option 1 as fallback")
                    self.select_answer(1)
                
                time.sleep(2)
                
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

# Configuration - ADD YOUR API KEY HERE
# Important - ADD API KEY OR IT WON'T WORK
# ADD IT HERE ⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️
OPENROUTER_API_KEY = "YOUR API KEY HERE"

def main():
    print("🚀 ACADALLY QUIZ BOT")
    print("="*50)
    
    # Initialize bot
    bot = AcadallyBot(OPENROUTER_API_KEY)
    
    # Setup driver and open Acadally
    print("🌐 Launching browser and opening Acadally...")
    if not bot.setup_driver():
        print("❌ Failed to setup browser")
        return
    
    # Wait for user to login and start quiz
    bot.wait_for_user_ready()
    
    # Start automation
    bot.run_quiz_automation()
    
    # Keep browser open
    input("\nPress Enter to close this window...")

if __name__ == "__main__":
    main()