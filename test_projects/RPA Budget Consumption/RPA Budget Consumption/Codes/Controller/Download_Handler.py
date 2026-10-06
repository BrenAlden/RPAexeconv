import logging
import time
import os
import shutil
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime

def get_fiscal_year():
    now = datetime.now()
    if now.month >= 4:  # Apr-Dec
        return now.year
    else:               # Jan-Mar
        return now.year - 1

def set_fy_filter(driver, target_year="2026"):
    try:
        wait = WebDriverWait(driver, 20)
        logging.info("Looking for FY GL ACTUAL slicer inside iframe...")

        driver.switch_to.default_content()
        driver.switch_to.frame(0)

        # Combobox[3] adalah FY GL ACTUAL (text='2025')
        all_dropdowns = wait.until(
            lambda d: d.find_elements(By.XPATH, "//*[@role='combobox']")
        )

        fy_dropdown = None
        for dd in all_dropdowns:
            try:
                text  = dd.text or ""
                inner = dd.get_attribute('innerHTML') or ""
                if any(str(y) in text or str(y) in inner for y in range(2020, 2030)):
                    fy_dropdown = dd
                    break
            except:
                continue

        if fy_dropdown is None:
            fy_dropdown = all_dropdowns[-1]

        driver.execute_script("arguments[0].click();", fy_dropdown)
        logging.info("FY GL ACTUAL dropdown clicked.")
        time.sleep(2)

        # Power BI pakai checkbox list, bukan role='option'
        # Uncheck semua tahun yang ter-check dulu, lalu check target_year
        checkbox_xpath = "//*[contains(@class, 'slicerItemContainer')] | //*[contains(@class, 'slicer-item')]"
        checkboxes = wait.until(lambda d: d.find_elements(By.XPATH, checkbox_xpath))
        logging.info(f"Found {len(checkboxes)} checkbox items in FY dropdown.")

        for cb in checkboxes:
            try:
                label = cb.text.strip()
                # Uncheck yang sedang aktif (bukan target)
                if label and label != str(target_year):
                    aria = cb.get_attribute("aria-selected") or ""
                    css_class = cb.get_attribute("class") or ""
                    is_checked = aria == "true" or "selected" in css_class or "checked" in css_class
                    if is_checked:
                        driver.execute_script("arguments[0].click();", cb)
                        logging.info(f"Unchecked: {label}")
                        time.sleep(0.5)
            except:
                continue

        # Check target_year
        target_xpath = (
            f"//*[contains(@class, 'slicerItemContainer') and normalize-space(.)='{target_year}'] | "
            f"//*[contains(@class, 'slicer-item') and normalize-space(.)='{target_year}'] | "
            f"//*[contains(@class, 'row') and normalize-space(text())='{target_year}']"
        )
        target_cb = wait.until(EC.element_to_be_clickable((By.XPATH, target_xpath)))
        driver.execute_script("arguments[0].click();", target_cb)
        logging.info(f"Year {target_year} checked.")
        time.sleep(3)

        # Tetap di dalam iframe — execute_report_download butuh konteks iframe
        return True

    except Exception as e:
        driver.switch_to.default_content()
        logging.error(f"Failed to set FY filter: {str(e).splitlines()[0]}")
        return False

def execute_report_download(driver):
    try:
        wait = WebDriverWait(driver, 20)

        # Set filter FY GL ACTUAL ke 2026 sebelum download
        # Setelah set_fy_filter, driver sudah di dalam iframe index 0
        if not set_fy_filter(driver, target_year="2026"):
            raise Exception("Failed to set FY GL ACTUAL filter to 2026.")

        logging.info("Attempting to touch the table center inside iframe...")
        # Tidak perlu switch_to.frame lagi — sudah di dalam iframe dari set_fy_filter
        visual_xpath = "//*[contains(@class, 'visual-container')] | //*[@role='region']"
        table_visual = wait.until(EC.element_to_be_clickable((By.XPATH, visual_xpath)))
        
        actions = ActionChains(driver)
        actions.move_to_element(table_visual).click().perform()
        logging.info("Table clicked.")
        time.sleep(3) 

        dots_xpath = "//button[@aria-label='More options']"
        dots_button = wait.until(EC.element_to_be_clickable((By.XPATH, dots_xpath)))
        driver.execute_script("arguments[0].click();", dots_button)
        logging.info("Three dots menu clicked.")
        time.sleep(3) 

        export_xpath = "//*[contains(text(), 'Export')] | //*[contains(text(), 'Ekspor')]"
        export_item = None
        
        for context in ["iframe", "main"]:
            try:
                if context == "main": driver.switch_to.default_content()
                items = driver.find_elements(By.XPATH, export_xpath)
                for item in items:
                    if "data" in item.text.lower() or "data" in item.get_attribute("innerHTML").lower():
                        if item.is_displayed():
                            export_item = item
                            break
                if export_item: break
            except:
                if context == "iframe": driver.switch_to.frame(0)
                continue

        if not export_item:
            raise Exception("Could not find visible 'Export data' menu item.")

        driver.execute_script("arguments[0].click();", export_item)
        logging.info("Export data menu item clicked.")

        logging.info("Waiting for final Export confirmation modal...")
        time.sleep(4)

        driver.switch_to.default_content()
        
        final_export_selector = "button[data-testid='export-btn']"
        
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        button_clicked = False
            
        for i in range(len(iframes)):
            try:
                driver.switch_to.default_content()
                driver.switch_to.frame(i)
                final_btn = driver.find_element(By.CSS_SELECTOR, final_export_selector)
                if final_btn.is_displayed():
                    driver.execute_script("arguments[0].click();", final_btn)
                    logging.info(f"Final Export button clicked in Iframe index {i}.")
                    button_clicked = True
                    break
            except:
                continue
            
            if not button_clicked:
                raise Exception("All attempts to click the final Export button failed.")

        logging.info("Download initiated. Waiting 15 seconds for file to generate...")
        time.sleep(15) 
        return True

            
    except Exception as e:
        logging.error(f"Failed at Export sequence: {str(e).splitlines()[0]}")
        return False


def move_downloaded_file(target_directory):
    try:
        download_path = os.path.join(os.path.expanduser('~'), 'Downloads')
        
        files = [
            os.path.join(download_path, f) for f in os.listdir(download_path) 
            if f.endswith(('.xlsx', '.csv')) and not f.startswith('~$')
        ]
        
        if not files:
            logging.warning("No valid Excel/CSV files found in Downloads.")
            return None

        latest_file = max(files, key=os.path.getctime)
        
        # Validasi waktu (file harus baru/fresh)
        if time.time() - os.path.getctime(latest_file) > 120:  # Toleransi 2 menit
            logging.warning("The latest file is too old. Download might have failed.")
            return None

        if not os.path.exists(target_directory):
            os.makedirs(target_directory, exist_ok=True)

        file_name = os.path.basename(latest_file)
        destination_path = os.path.join(target_directory, file_name)

        shutil.move(latest_file, destination_path)
        logging.info(f"Success! File moved to: {destination_path}")
        return destination_path

    except Exception as e:
        logging.error(f"Failed to move file: {str(e)}")
        return None