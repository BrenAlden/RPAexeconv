from selenium import webdriver

def start_browser():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_experimental_option("detach", True)

    options.add_argument("--log-level=3")  
    options.add_experimental_option('excludeSwitches', ['enable-logging'])

    try:
        driver = webdriver.Chrome(options=options)
        return driver
    except Exception as e:
        print(f"Failed to start browser: {e}")
        return None