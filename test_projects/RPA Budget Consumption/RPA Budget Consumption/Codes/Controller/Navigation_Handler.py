import logging
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def login_and_go_to_rpa(driver, url):
    try:
        logging.info(f"Navigating to: {url}")
        driver.get(url)
        
        wait = WebDriverWait(driver, 600)
        time.sleep(10) 

        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        logging.info(f"Found {len(iframes)} iframes on page.")
        
        for index, frame in enumerate(iframes):
            driver.switch_to.default_content()
            driver.switch_to.frame(index)

            if len(driver.find_elements(By.XPATH, "//div[@title='RPA']")) > 0:
                logging.info(f"Successfully switched to report iframe at index {index}")
                break
        
        rpa_tab_xpath = "//div[@title='RPA']"
        tab_element = wait.until(EC.element_to_be_clickable((By.XPATH, rpa_tab_xpath)))
        tab_element.click()
        
        return True
    except Exception as e:
        logging.error(f"Navigation Error: {str(e)}")
        return False