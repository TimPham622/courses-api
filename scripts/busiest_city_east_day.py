#!/usr/bin/env python3
"""Find the busiest weekday for Semester 2 classes at the City East campus.

The script calls the Courses API rather than reading the database directly.

Example:
    python scripts/busiest_city_east_day.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TERM = "Semester 2"
DEFAULT_CAMPUS = "City East"
WEEKDAY_ORDER = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Call the Courses API and print the busiest weekday plus the number "
            "of Semester 2 City East classes."
        )
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("COURSES_API_BASE_URL", DEFAULT_BASE_URL),
        help=(
            "Base URL for the Courses API. Defaults to COURSES_API_BASE_URL or "
            f"{DEFAULT_BASE_URL}."
        ),
    )
    parser.add_argument(
        "--year",
        type=int,
        default=datetime.now().year,
        help="Course year to analyse. Defaults to the current year.",
    )
    parser.add_argument(
        "--term",
        default=DEFAULT_TERM,
        help=f"Teaching term to analyse. Defaults to {DEFAULT_TERM!r}.",
    )
    parser.add_argument(
        "--campus",
        default=DEFAULT_CAMPUS,
        help=f"Campus to analyse. Defaults to {DEFAULT_CAMPUS!r}.",
    )
    return parser.parse_args()


def api_get(base_url: str, path: str, params: dict[str, Any] | None = None) -> Any:
    query = f"?{urlencode(params)}" if params else ""
    url = f"{base_url.rstrip('/')}{path}{query}"
    request = Request(url, headers={"Accept": "application/json"})

    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API request failed: {url} returned {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not connect to the Courses API at {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"API response was not valid JSON for {url}") from exc


def normalise(value: Any) -> str:
    return str(value or "").strip().casefold()


def campus_matches(value: Any, target_campus: str) -> bool:
    return normalise(target_campus) in normalise(value)


def get_subjects(base_url: str, year: int, term: str) -> list[str]:
    subjects = api_get(base_url, "/subjects", {"year": year, "term": term})
    if not isinstance(subjects, list):
        raise RuntimeError("/subjects did not return a list")
    return [str(subject) for subject in subjects]


def get_courses(base_url: str, subject: str, year: int, term: str) -> list[dict[str, Any]]:
    payload = api_get(
        base_url,
        "/courses",
        {"subject": subject, "year": year, "term": term},
    )
    courses = payload.get("courses", []) if isinstance(payload, dict) else payload
    if not isinstance(courses, list):
        raise RuntimeError(f"/courses did not return a course list for subject {subject!r}")
    return [course for course in courses if isinstance(course, dict)]


def count_classes_by_day(
    course_details: dict[str, Any],
    target_campus: str,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    course_is_on_campus = campus_matches(course_details.get("campus"), target_campus)

    for class_group in course_details.get("class_list", []):
        for class_item in class_group.get("classes", []):
            for meeting in class_item.get("meetings", []):
                day = meeting.get("day")
                meeting_campus = meeting.get("campus")

                if day not in WEEKDAY_ORDER:
                    continue

                if campus_matches(meeting_campus, target_campus) or (
                    not meeting_campus and course_is_on_campus
                ):
                    counts[day] += 1

    return counts


def find_busiest_day(base_url: str, year: int, term: str, campus: str) -> tuple[str, int]:
    subjects = get_subjects(base_url, year, term)
    course_ids: set[str] = set()

    for subject in subjects:
        for course in get_courses(base_url, subject, year, term):
            if not campus_matches(course.get("campus"), campus):
                continue

            course_id = course.get("id")
            if course_id:
                course_ids.add(str(course_id))

    day_counts: Counter[str] = Counter()
    for course_id in sorted(course_ids):
        details = api_get(base_url, f"/courses/{course_id}")
        if isinstance(details, dict):
            day_counts.update(count_classes_by_day(details, campus))

    if not day_counts:
        return "No classes found", 0

    busiest_day = max(
        WEEKDAY_ORDER,
        key=lambda day: (day_counts[day], -WEEKDAY_ORDER.index(day)),
    )
    return busiest_day, day_counts[busiest_day]


def main() -> int:
    args = parse_args()

    try:
        day, class_count = find_busiest_day(
            args.base_url,
            args.year,
            args.term,
            args.campus,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    noun = "class" if class_count == 1 else "classes"
    print(f"{day}: {class_count} {noun}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
