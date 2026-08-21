"""
AcadAlly Automizer

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
            
            # Prepare the prompt - SIMPLIFIED!
            prompt = f"""
            Question: {visible_text}
            
            Answer with ONLY: ANSWER: X
            Where X is A, B, C, or D
            
            Example: ANSWER: B
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
                "max_tokens": 30
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
                
                # Extract the answer letter (A, B, C, D) and convert to number
                import re
                match = re.search(r'ANSWER:\s*([A-D])', answer_text, re.IGNORECASE)
                if match:
                    answer_letter = match.group(1).upper()
                    # Convert letter to number: A=1, B=2, C=3, D=4
                    answer_num = ord(answer_letter) - ord('A') + 1
                    print(f"✅ Extracted answer: Option {answer_letter} (Number {answer_num})")
                    return answer_num
                else:
                    # Fallback: look for any letter A-D
                    letters = re.findall(r'\b([A-D])\b', answer_text, re.IGNORECASE)
                    if letters:
                        answer_letter = letters[0].upper()
                        answer_num = ord(answer_letter) - ord('A') + 1
                        print(f"✅ Found letter in response: Option {answer_letter} (Number {answer_num})")
                        return answer_num
                    
            print("❌ Could not extract answer")
            return None
            
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
                
                if correct_option is None:
                    print("\n❌ Could not extract answer")
                    print("❌ Stopping on this question to avoid incorrect answer")
                    print("❌ Please check the AI response above and manually answer this question")
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

# Configuration - ADD YOUR API KEY HERE
# Important - ADD API KEY OR IT WON'T WORK
# ADD IT HERE ⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️
OPENROUTER_API_KEY = "YOUR API KEY HERE "

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
    
    while True:
        # Wait for user to login and start quiz
        bot.wait_for_user_ready()
        
        # Start automation
        bot.run_quiz_automation()
        
        # Ask if user wants to do another quiz
        print("\n" + "="*50)
        response = input("Do you want to do another quiz? (y/n): ").strip().lower()
        
        if response != 'y':
            break
        else:
            print("\nPlease navigate to the new quiz and get to the first question...")
    
    # Keep browser open
    input("\nPress Enter to close this window...")

if __name__ == "__main__":
    main()