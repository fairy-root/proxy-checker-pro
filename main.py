import requests
import concurrent.futures
import re
import socket
from time import time
from colorama import Fore, Style, init
from tqdm import tqdm

INPUT_FILE = "proxies.txt"
WORKING_FILE = "working.txt"
DOWN_FILE = "down.txt"
TARGET_URL = "https://www.google.com"
VALIDATION_TEXT = "<title>Google</title>"
REQUEST_TIMEOUT = 10
MAX_WORKERS = 50

init(autoreset=True)


def parse_proxy(proxy_line):
    """
    Parses a proxy line into a dictionary.
    Handles formats:
    (Type)Host:Port
    (Type)Host:Port:User:Pass
    """
    proxy_line = proxy_line.strip()
    if not proxy_line:
        return None

    pattern = re.compile(r"\((\w+)\)([^:]+):(\d+)(?::([^:]+):(.*))?")
    match = pattern.match(proxy_line)

    if not match:
        print(f"{Fore.YELLOW}Warning: Skipping malformed proxy line: {proxy_line}")
        return None

    proto, host, port, user, password = match.groups()
    proto = proto.lower()

    if proto not in ["http", "socks5"]:
        print(
            f"{Fore.YELLOW}Warning: Skipping unsupported protocol '{proto}' in line: {proxy_line}"
        )
        return None

    return {
        "original": proxy_line,
        "protocol": proto,
        "host": host,
        "port": int(port),
        "user": user,
        "password": password,
    }


def get_country(host):
    """Gets the country of a host (IP or domain) using a free geo-IP API."""
    ip_address = host
    try:

        ip_address = socket.gethostbyname(host)
    except socket.gaierror:
        return "N/A (DNS Error)"

    try:

        response = requests.get(
            f"http://ip-api.com/json/{ip_address}?fields=country", timeout=5
        )
        response.raise_for_status()
        data = response.json()
        return data.get("country", "N/A")
    except requests.exceptions.RequestException:
        return "N/A (Geo-IP Error)"


def check_proxy(proxy_info):
    """
    Checks a single proxy and returns a dictionary with the results.
    """
    if not proxy_info:
        return None

    protocol = proxy_info["protocol"]
    host = proxy_info["host"]
    port = proxy_info["port"]
    user = proxy_info["user"]
    password = proxy_info["password"]

    if user and password:
        proxy_url = f"{protocol}://{user}:{password}@{host}:{port}"
    else:
        proxy_url = f"{protocol}://{host}:{port}"

    proxies_dict = {"http": proxy_url, "https": proxy_url}

    result = {
        "proxy": proxy_info["original"],
        "status": "Inactive",
        "ping": -1,
        "country": "N/A",
        "error": "Unknown",
    }

    try:

        result["country"] = get_country(host)

        start_time = time()
        response = requests.get(
            TARGET_URL,
            proxies=proxies_dict,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            },
        )
        end_time = time()

        result["ping"] = round((end_time - start_time) * 1000)

        if response.status_code == 200 and VALIDATION_TEXT in response.text:
            result["status"] = "Active"
            result.pop("error", None)
        else:
            result["error"] = f"Status: {response.status_code}, Validation Failed"

    except requests.exceptions.ProxyError as e:
        result["error"] = "Proxy Error"
    except requests.exceptions.ConnectTimeout:
        result["error"] = "Timeout"
    except requests.exceptions.ConnectionError:
        result["error"] = "Connection Error"
    except requests.exceptions.RequestException as e:
        result["error"] = f"Request Error"
    except Exception as e:
        result["error"] = "General Error"

    return result


def main():
    """
    Main function to read proxies, check them, and save results.
    """
    try:
        with open(INPUT_FILE, "r") as f:
            proxy_lines = f.readlines()
    except FileNotFoundError:
        print(f"{Fore.RED}Error: The input file '{INPUT_FILE}' was not found.")
        return

    parsed_proxies = [parse_proxy(line) for line in proxy_lines]

    valid_proxies = [p for p in parsed_proxies if p is not None]

    if not valid_proxies:
        print(f"{Fore.YELLOW}No valid proxies found in '{INPUT_FILE}'.")
        return

    print(
        f"{Style.BRIGHT}Starting check for {len(valid_proxies)} proxies with {MAX_WORKERS} threads..."
    )
    print("-" * 80)

    working_count = 0
    down_count = 0

    with open(WORKING_FILE, "w") as wf, open(DOWN_FILE, "w") as df:

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

            future_to_proxy = {
                executor.submit(check_proxy, proxy_info): proxy_info
                for proxy_info in valid_proxies
            }

            for future in tqdm(
                concurrent.futures.as_completed(future_to_proxy),
                total=len(valid_proxies),
                desc="Checking Proxies",
            ):
                res = future.result()
                if not res:
                    continue

                if res["status"] == "Active":
                    working_count += 1
                    status_colored = f"{Fore.GREEN}{res['status']:<8}"
                    ping_str = f"{res['ping']} ms"

                    wf.write(res["proxy"] + "\n")
                    print(
                        f"{status_colored} | "
                        f"{Fore.CYAN}Ping: {ping_str:<8} | "
                        f"{Fore.YELLOW}Country: {res['country']:<20} | "
                        f"{Style.BRIGHT}Proxy: {res['proxy']}"
                    )
                else:
                    down_count += 1
                    status_colored = f"{Fore.RED}{res['status']:<8}"

                    df.write(res["proxy"] + "\n")
                    print(
                        f"{status_colored} | "
                        f"{Fore.CYAN}Ping: {'N/A':<8} | "
                        f"{Fore.YELLOW}Country: {res['country']:<20} | "
                        f"{Style.BRIGHT}Proxy: {res['proxy']} ({res['error']})"
                    )

    print("-" * 80)
    print(f"{Style.BRIGHT}Check Complete!")
    print(f"{Fore.GREEN}Total Working: {working_count}")
    print(f"{Fore.RED}Total Down: {down_count}")
    print(f"Results saved to '{WORKING_FILE}' and '{DOWN_FILE}'.")


if __name__ == "__main__":
    main()
