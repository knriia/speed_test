#!/usr/bin/env python3
"""Measure download speed by fetching one URL ten times in sequence."""

import argparse
import math
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


REQUEST_COUNT = 10
CHUNK_SIZE = 64 * 1024
DEFAULT_TIMEOUT = 30


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            f"Download a URL {REQUEST_COUNT} times in sequence and report "
            "the average response time and download speed."
        )
    )
    parser.add_argument("url", help="direct HTTP or HTTPS URL to a file, such as an image")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"timeout for each request in seconds (default: {DEFAULT_TIMEOUT})",
    )
    args = parser.parse_args()

    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    try:
        parts = urlsplit(args.url)
        port = parts.port
    except ValueError:
        parser.error("URL is malformed")

    if parts.scheme not in {"http", "https"} or not parts.hostname:
        parser.error("URL must be an absolute HTTP or HTTPS address")
    args.server = parts.hostname + (f":{port}" if port is not None else "")

    return args


def download_once(url: str, timeout: float) -> tuple[int, float]:
    request = Request(url, headers={"Cache-Control": "no-cache"})
    started_at = time.perf_counter()
    downloaded_bytes = 0

    with urlopen(request, timeout=timeout) as response:
        if not 200 <= response.status < 300:
            raise OSError(f"unexpected HTTP status {response.status}")

        while chunk := response.read(CHUNK_SIZE):
            downloaded_bytes += len(chunk)

    return downloaded_bytes, time.perf_counter() - started_at


def main() -> int:
    args = parse_args()
    successful_requests = 0
    failed_requests = 0
    total_bytes = 0
    total_request_seconds = 0.0

    print(f"Сервер: {args.server}")
    print(f"Выполняю {REQUEST_COUNT} последовательных запросов...\n")

    for request_number in range(1, REQUEST_COUNT + 1):
        try:
            downloaded_bytes, elapsed_seconds = download_once(args.url, args.timeout)
        except HTTPError as error:
            failed_requests += 1
            print(f"[{request_number}/{REQUEST_COUNT}] ошибка: HTTP {error.code}")
            error.close()
        except (URLError, OSError, TimeoutError) as error:
            failed_requests += 1
            if isinstance(error, URLError) and isinstance(error.reason, TimeoutError):
                message = "тайм-аут"
            else:
                message = "ошибка сети или чтения ответа"
            print(f"[{request_number}/{REQUEST_COUNT}] ошибка: {message}")
        else:
            successful_requests += 1
            total_bytes += downloaded_bytes
            total_request_seconds += elapsed_seconds
            print(
                f"[{request_number}/{REQUEST_COUNT}] скачано {downloaded_bytes:,} байт "
                f"за {elapsed_seconds:.3f} с"
            )

    print("\nИтог:")
    print(f"Успешных запросов: {successful_requests}/{REQUEST_COUNT}")
    print(f"Скачано всего: {total_bytes:,} байт ({total_bytes / 1_000_000:.3f} МБ)")

    if successful_requests:
        average_seconds = total_request_seconds / successful_requests
        print(f"Среднее время запроса: {average_seconds:.3f} с")
        if total_request_seconds > 0:
            speed_mb_per_second = total_bytes / total_request_seconds / 1_000_000
            print(f"Средняя скорость загрузки: {speed_mb_per_second:.3f} МБ/с")
            print("(1 МБ = 1 000 000 байт; скорость рассчитана по успешным запросам.)")
        else:
            print("Средняя скорость загрузки: не удалось измерить")
    else:
        print("Среднее время запроса: нет успешных запросов")
        print("Средняя скорость загрузки: не удалось измерить")

    return 1 if failed_requests else 0


if __name__ == "__main__":
    sys.exit(main())
