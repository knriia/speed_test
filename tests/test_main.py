import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from urllib.error import URLError
from unittest.mock import call, patch

import main


URL = "https://example.org/large-image.jpg"


class FakeResponse:
    status = 200

    def __init__(self, chunks):
        self._chunks = iter(chunks)
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, size):
        self.read_sizes.append(size)
        return next(self._chunks, b"")


class DownloadOnceTests(unittest.TestCase):
    def test_counts_streamed_bytes_and_measures_elapsed_time(self):
        response = FakeResponse([b"ab", b"c", b""])

        with (
            patch.object(main, "urlopen", return_value=response) as urlopen,
            patch.object(main.time, "perf_counter", side_effect=[10.0, 12.5]),
        ):
            downloaded_bytes, elapsed_seconds = main.download_once(URL, 7)

        self.assertEqual(downloaded_bytes, 3)
        self.assertEqual(elapsed_seconds, 2.5)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 7)
        self.assertEqual(response.read_sizes, [main.CHUNK_SIZE] * 3)


class MainTests(unittest.TestCase):
    def run_main_with_downloads(self, download_side_effect):
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["main.py", URL]),
            patch.object(main, "download_once", side_effect=download_side_effect) as download,
            redirect_stdout(output),
        ):
            exit_code = main.main()
        return exit_code, output.getvalue(), download

    def test_performs_ten_sequential_requests_and_reports_totals(self):
        results = [(2_000_000, 4.0)] * main.REQUEST_COUNT
        exit_code, output, download = self.run_main_with_downloads(results)

        self.assertEqual(exit_code, 0)
        self.assertEqual(download.call_count, main.REQUEST_COUNT)
        self.assertEqual(
            download.call_args_list,
            [call(URL, main.DEFAULT_TIMEOUT)] * main.REQUEST_COUNT,
        )
        self.assertIn("Успешных запросов: 10/10", output)
        self.assertIn("Скачано всего: 20,000,000 байт (20.000 МБ)", output)
        self.assertIn("Среднее время запроса: 4.000 с", output)
        self.assertIn("Средняя скорость загрузки: 0.500 МБ/с", output)

    def test_continues_after_network_error_and_returns_failure_status(self):
        results = [(1_000_000, 2.0), URLError("network unavailable")]
        results.extend([(1_000_000, 2.0)] * (main.REQUEST_COUNT - 2))

        exit_code, output, download = self.run_main_with_downloads(results)

        self.assertEqual(exit_code, 1)
        self.assertEqual(download.call_count, main.REQUEST_COUNT)
        self.assertIn("Успешных запросов: 9/10", output)
        self.assertIn("Скачано всего: 9,000,000 байт (9.000 МБ)", output)
        self.assertIn("ошибка сети или чтения ответа", output)

    def test_reports_unavailable_speed_when_all_requests_fail(self):
        failures = [URLError("network unavailable")] * main.REQUEST_COUNT

        exit_code, output, download = self.run_main_with_downloads(failures)

        self.assertEqual(exit_code, 1)
        self.assertEqual(download.call_count, main.REQUEST_COUNT)
        self.assertIn("Успешных запросов: 0/10", output)
        self.assertIn("Среднее время запроса: нет успешных запросов", output)
        self.assertIn("Средняя скорость загрузки: не удалось измерить", output)


class ArgumentValidationTests(unittest.TestCase):
    def test_rejects_non_http_url(self):
        stderr = io.StringIO()
        with (
            patch.object(sys, "argv", ["main.py", "file:///tmp/image.jpg"]),
            redirect_stderr(stderr),
            self.assertRaises(SystemExit) as raised,
        ):
            main.parse_args()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("URL must be an absolute HTTP or HTTPS address", stderr.getvalue())

    def test_rejects_non_positive_timeout(self):
        stderr = io.StringIO()
        with (
            patch.object(sys, "argv", ["main.py", URL, "--timeout", "0"]),
            redirect_stderr(stderr),
            self.assertRaises(SystemExit) as raised,
        ):
            main.parse_args()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--timeout must be greater than zero", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
