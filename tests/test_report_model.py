"""Model of the report: ratings, aggregates, worst files, summary (SPEC §12.3)."""

import json
import unittest
from datetime import timedelta
from pathlib import Path

from furryp.config.defaults import DEFAULT_RATING_THRESHOLDS
from furryp.core.errors import FileFailure
from furryp.metrics.halstead import Halstead
from furryp.report.categories import NotRated, Share, build_categories, rating_of, stats
from furryp.report.model import Timing
from tests.report_support import (
    FIXED_TIME,
    ROOT,
    class_measures,
    failed,
    function,
    model_of,
    summary,
)
from tests.support import make_settings, real_registry


def category(key: str, files, data: dict[str, object] | None = None):
    """Return the category ``key`` of constructed files."""
    categories = build_categories(files, make_settings(data), real_registry())
    return next(item for item in categories if item.key == key)


def flagged(count: int, total: int, code: str = "FUR403") -> list:
    """Return ``total`` files, of which ``count`` have a violation of ``code``."""
    return [
        summary(f"{index}.py", violations={code: 1} if index < count else None)
        for index in range(total)
    ]


def worst_paths(key: str, files, data: dict[str, object] | None = None) -> list[str]:
    """Return the paths of the worst files of a category, in their order."""
    return [row["path"] for row in category(key, files, data).worst]


class RatingTest(unittest.TestCase):
    def test_default_thresholds_are_bands_of_20(self) -> None:
        self.assertEqual(DEFAULT_RATING_THRESHOLDS, (0.20, 0.40, 0.60, 0.80))

    def test_boundaries_with_the_default_thresholds(self) -> None:
        cases = (
            (0.0, "A"),
            (0.20, "A"),
            (0.2001, "B"),
            (0.40, "B"),
            (0.4001, "C"),
            (0.60, "C"),
            (0.6001, "D"),
            (0.80, "D"),
            (0.8001, "E"),
            (1.0, "E"),
        )
        for share, letter in cases:
            with self.subTest(share=share):
                self.assertEqual(rating_of(share, DEFAULT_RATING_THRESHOLDS), letter)

    def test_custom_thresholds(self) -> None:
        thresholds = (0.1, 0.2, 0.3, 0.4)
        self.assertEqual(rating_of(0.1, thresholds), "A")
        self.assertEqual(rating_of(0.3, thresholds), "C")
        self.assertEqual(rating_of(0.41, thresholds), "E")

    def test_exact_fractions_of_files_hit_the_boundaries(self) -> None:
        """1 file of 5 is exactly 20 %: A, not B."""
        for count, letter in (
            (0, "A"),
            (1, "A"),
            (2, "B"),
            (3, "C"),
            (4, "D"),
            (5, "E"),
        ):
            with self.subTest(count=count):
                result = category("design", flagged(count, 5))
                self.assertEqual(result.rating, letter)
                self.assertEqual(result.share, Share(count, 5))

    def test_thresholds_of_the_configuration(self) -> None:
        data = {"report": {"rating-thresholds": [0.5, 0.6, 0.7, 0.8]}}
        self.assertEqual(category("design", flagged(2, 5), data).rating, "A")

    def test_the_share_counts_files_not_violations(self) -> None:
        files = [summary("a.py", violations={"FUR403": 3}), summary("b.py")]
        result = category("design", files)
        self.assertEqual((result.share, result.rating), (Share(1, 2), "C"))

    def test_a_suppressed_violation_does_not_count(self) -> None:
        files = [summary(suppressed={"FUR403": 1}), summary("b.py")]
        result = category("design", files)
        self.assertEqual((result.rating, result.share), ("A", Share(0, 2)))

    def test_each_category_only_counts_its_rules(self) -> None:
        files = [summary(violations={"FUR101": 1})]
        self.assertEqual(category("size", files).rating, "E")
        self.assertEqual(category("complexity", files).rating, "A")
        self.assertEqual(category("halstead", files).rating, "A")
        self.assertEqual(category("design", files).rating, "A")


class NotRatedTest(unittest.TestCase):
    def test_no_rule_of_the_category_is_selected(self) -> None:
        result = category("size", [summary()], {"select": ["FUR4"]})
        self.assertIsNone(result.rating)
        self.assertIs(result.not_rated, NotRated.NO_RULE)
        self.assertEqual(result.rules, ())

    def test_a_selected_rule_keeps_the_rating(self) -> None:
        result = category("design", [summary()], {"select": ["FUR4"]})
        self.assertEqual(result.rating, "A")
        self.assertIsNone(result.not_rated)

    def test_a_category_with_one_selected_rule_is_rated(self) -> None:
        result = category("size", [summary()], {"ignore": ["FUR101"]})
        self.assertEqual(result.rating, "A")
        self.assertEqual([row.code for row in result.rules], ["FUR102"])

    def test_no_file_was_analyzed(self) -> None:
        result = category("size", [])
        self.assertIsNone(result.rating)
        self.assertIs(result.not_rated, NotRated.NO_FILE)


class WorstFilesTest(unittest.TestCase):
    def test_a_file_without_violation_is_not_listed(self) -> None:
        """A huge file whose scores are fine is not a bad file."""
        files = [
            summary("huge.py", code_lines=5000),
            summary("small.py", code_lines=10, violations={"FUR101": 1}),
        ]
        self.assertEqual(worst_paths("size", files), ["small.py"])

    def test_no_violation_gives_an_empty_table(self) -> None:
        for key in ("size", "complexity", "halstead", "design", "design"):
            with self.subTest(key=key):
                self.assertEqual(worst_paths(key, [summary()]), [])

    def test_from_the_worst_score_to_the_best(self) -> None:
        files = [
            summary("low.py", code_lines=10, violations={"FUR101": 1}),
            summary("high.py", code_lines=30, violations={"FUR101": 1}),
            summary("mid.py", code_lines=20, violations={"FUR101": 1}),
        ]
        self.assertEqual(worst_paths("size", files), ["high.py", "mid.py", "low.py"])

    def test_on_a_tie_the_longest_file_comes_first_then_the_path(self) -> None:
        files = [
            summary("b_short.py", lines=10, violations={"FUR403": 1}),
            summary("c_long.py", lines=99, violations={"FUR403": 1}),
            summary("a_short.py", lines=10, violations={"FUR403": 1}),
        ]
        self.assertEqual(
            worst_paths("design", files),
            ["c_long.py", "a_short.py", "b_short.py"],
        )

    def test_design_ties_also_go_to_the_longest_file(self) -> None:
        files = [
            summary(
                "complex.py",
                lines=10,
                classes=[class_measures(complexity=60)],
                violations={"FUR403": 1},
            ),
            summary("long.py", lines=99, violations={"FUR403": 1}),
        ]
        self.assertEqual(worst_paths("design", files), ["long.py", "complex.py"])

    def test_limited_to_ten_by_default(self) -> None:
        self.assertEqual(len(worst_paths("design", flagged(12, 12))), 10)

    def test_limited_to_top_n_of_the_configuration(self) -> None:
        for key, code in (
            ("size", "FUR101"),
            ("complexity", "FUR203"),
            ("halstead", "FUR202"),
            ("design", "FUR401"),
        ):
            with self.subTest(key=key):
                files = flagged(5, 5, code)
                self.assertEqual(
                    len(worst_paths(key, files, {"report": {"top-n": 3}})), 3
                )

    def test_top_n_of_zero(self) -> None:
        self.assertEqual(
            worst_paths("design", flagged(2, 2), {"report": {"top-n": 0}}), []
        )

    def test_a_suppressed_violation_is_not_listed(self) -> None:
        files = [summary(suppressed={"FUR403": 1})]
        self.assertEqual(worst_paths("design", files), [])

    def test_a_deselected_rule_lists_nothing(self) -> None:
        files = flagged(3, 3, "FUR403")
        result = category("size", files, {"select": ["FUR403"]})
        self.assertEqual(result.worst, ())


class AggregatesTest(unittest.TestCase):
    def test_statistics(self) -> None:
        self.assertEqual(
            stats("x", [1, 2, 6]),
            {"x_mean": 3.0, "x_median": 2.0, "x_max": 6, "x_total": 9},
        )

    def test_median_of_an_even_count(self) -> None:
        self.assertEqual(stats("x", [1, 2])["x_median"], 1.5)

    def test_statistics_of_nothing(self) -> None:
        self.assertEqual(set(stats("x", []).values()), {None})

    def test_size(self) -> None:
        files = [
            summary(
                "a.py", lines=10, code_lines=4, functions=[function(code_lines=30)]
            ),
            summary(
                "b.py",
                lines=20,
                code_lines=8,
                functions=[function(code_lines=26), function(code_lines=25)],
            ),
        ]
        aggregates = category("size", files).aggregates
        self.assertEqual(aggregates["lines_total"], 30)
        self.assertEqual(aggregates["code_lines_mean"], 6.0)
        self.assertEqual(aggregates["function_lines_max"], 30)
        self.assertEqual(aggregates["functions_over"], 2)
        self.assertEqual(aggregates["function_limit"], 25)

    def test_a_nested_function_counts_alone_for_size_and_halstead(self) -> None:
        """A13: evaluated alone by FUR101 and FUR202, in its parent for FUR203."""
        measures = Halstead(10, 10, 100, 100)
        file = summary(
            functions=[
                function("outer", code_lines=30, halstead=measures),
                function("outer.inner", code_lines=40, nested=True, halstead=measures),
            ]
        )
        size = category("size", [file]).aggregates
        self.assertEqual(size["function_lines_max"], 40)
        self.assertEqual(size["functions_over"], 2)
        halstead = category("halstead", [file]).aggregates
        self.assertEqual(halstead["function_volume_total"], measures.volume * 2)

    def test_limits_come_from_the_configuration(self) -> None:
        file = summary(
            functions=[function(code_lines=10, cognitive=10)],
            classes=[class_measures(complexity=10, attributes=10)],
        )
        data = {
            "rules": {
                "function-too-long": {"max-lines": 9},
                "cognitive-complexity": {"max": 9},
                "too-complex-class": {"max-class-complexity": 9},
                "too-many-instance-attributes": {"max-instance-attributes": 9},
            }
        }
        self.assertEqual(category("size", [file], data).aggregates["function_limit"], 9)
        self.assertEqual(category("size", [file], data).aggregates["functions_over"], 1)
        complexity = category("complexity", [file], data).aggregates
        self.assertEqual(
            (complexity["cognitive_limit"], complexity["functions_over"]), (9, 1)
        )
        design = category("design", [file], data).aggregates
        self.assertEqual(
            (design["complexity_limit"], design["attributes_limit"]), (9, 9)
        )
        self.assertEqual(design["complexity_over"], Share(1, 1))
        self.assertEqual(design["attributes_over"], Share(1, 1))

    def test_a_value_at_the_limit_is_not_above_it(self) -> None:
        file = summary(functions=[function(code_lines=25, cognitive=20)])
        self.assertEqual(category("size", [file]).aggregates["functions_over"], 0)
        self.assertEqual(category("complexity", [file]).aggregates["functions_over"], 0)

    def test_design_row_shows_the_largest_values(self) -> None:
        file = summary(
            classes=[
                class_measures(complexity=3, attributes=9),
                class_measures(complexity=8, attributes=2),
            ],
            violations={"FUR403": 1},
        )
        row = category("design", [file]).worst[0]
        self.assertEqual((row["max_complexity"], row["max_attributes"]), (8, 9))

    def test_design_row_sees_the_same_classes_as_the_rules(self) -> None:
        file = summary(
            classes=[
                class_measures(complexity=3, attributes=2),
                class_measures(complexity=90, attributes=90, is_test=True),
                class_measures(complexity=90, is_dispatch=True),
                class_measures(attributes=90, is_data=True),
            ],
            violations={"FUR403": 1},
        )
        row = category("design", [file]).worst[0]
        self.assertEqual((row["max_complexity"], row["max_attributes"]), (3, 2))

    def test_figures_of_a_rule_that_did_not_run_are_unknown(self) -> None:
        data: dict[str, object] = {"select": ["FUR101"]}
        file = summary()
        design = category("design", [file], data).aggregates
        self.assertIsNone(design["contracts"])
        self.assertIsNone(design["chains"])
        self.assertIsNone(model_of([file], data).summary.unused_foqa)

    def test_size_row(self) -> None:
        file = summary(
            lines=9,
            code_lines=7,
            functions=[function("a", code_lines=2), function("b", code_lines=5)],
            violations={"FUR101": 1},
        )
        self.assertEqual(
            category("size", [file]).worst,
            (
                {
                    "path": "a.py",
                    "lines": 9,
                    "code_lines": 7,
                    "functions": 2,
                    "longest": "b (5)",
                },
            ),
        )

    def test_size_row_counts_nested_functions(self) -> None:
        """A13: a nested function counts alone, and it can be the longest."""
        file = summary(
            functions=[
                function("outer", code_lines=30),
                function("outer.inner", code_lines=40, nested=True),
            ],
            violations={"FUR101": 2},
        )
        row = category("size", [file]).worst[0]
        self.assertEqual(row["functions"], 2)
        self.assertEqual(row["longest"], "outer.inner (40)")

    def test_size_row_of_a_file_without_function(self) -> None:
        row = category("size", [summary(violations={"FUR102": 1})]).worst[0]
        self.assertIsNone(row["longest"])

    def test_complexity_leaves_out_nested_functions(self) -> None:
        file = summary(
            functions=[
                function("outer", cognitive=25),
                function("outer.inner", nested=True),
                function("simple", cognitive=5),
            ],
            violations={"FUR203": 1},
        )
        result = category("complexity", [file])
        self.assertEqual(result.aggregates["cognitive_total"], 30)
        self.assertEqual(result.aggregates["cognitive_mean"], 15.0)
        self.assertEqual(result.aggregates["functions_over"], 1)
        self.assertEqual(
            result.worst,
            ({"path": "a.py", "sum": 30, "max": 25, "function": "outer (25)"},),
        )

    def test_complexity_ranks_by_the_sum(self) -> None:
        """Against the alphabet and the length: only the score can give this order."""
        files = [
            summary(
                "a_one.py",
                lines=99,
                functions=[function(cognitive=30)],
                violations={"FUR203": 1},
            ),
            summary(
                "z_many.py",
                lines=1,
                functions=[function(cognitive=21), function(cognitive=21)],
                violations={"FUR203": 2},
            ),
        ]
        self.assertEqual(worst_paths("complexity", files), ["z_many.py", "a_one.py"])

    def test_design_ranks_by_the_number_of_violations(self) -> None:
        files = [
            summary("a_few.py", lines=99, violations={"FUR403": 1}),
            summary("z_many.py", lines=1, violations={"FUR403": 3}),
        ]
        self.assertEqual(worst_paths("design", files), ["z_many.py", "a_few.py"])

    def test_design_counts_every_rule_of_the_category_in_its_score(self) -> None:
        files = [
            summary("a.py", violations={"FUR401": 1, "FUR404": 1}),
            summary("b.py", violations={"FUR403": 3}),
            summary("c.py", violations={"FUR101": 9, "FUR402": 1}),
        ]
        self.assertEqual(worst_paths("design", files), ["b.py", "a.py", "c.py"])

    def test_halstead_ranks_by_the_configured_metric(self) -> None:
        big_volume = Halstead(2, 100, 2000, 2000)
        big_difficulty = Halstead(50, 2, 50, 500)
        self.assertGreater(big_volume.volume, big_difficulty.volume)
        self.assertGreater(big_difficulty.difficulty, big_volume.difficulty)
        files = [
            summary("volume.py", halstead=big_volume, violations={"FUR201": 1}),
            summary("difficulty.py", halstead=big_difficulty, violations={"FUR201": 1}),
        ]
        self.assertEqual(worst_paths("halstead", files)[0], "volume.py")
        data = {"rules": {"halstead-file": {"metric": "difficulty"}}}
        self.assertEqual(worst_paths("halstead", files, data)[0], "difficulty.py")
        self.assertEqual(
            category("halstead", files, data).aggregates["metric"], "difficulty"
        )

    def test_halstead_aggregates(self) -> None:
        measures = Halstead(10, 10, 100, 100)
        files = [
            summary("a.py", halstead=measures, functions=[function(halstead=measures)]),
            summary("b.py"),
        ]
        aggregates = category("halstead", files).aggregates
        self.assertEqual(aggregates["volume_max"], measures.volume)
        self.assertEqual(aggregates["bugs_total"], measures.bugs)
        self.assertEqual(aggregates["function_volume_mean"], measures.volume)

    def test_design_sees_the_same_classes_as_the_rules(self) -> None:
        classes = [
            class_measures("Plain", complexity=80, attributes=20),
            class_measures("Tests", complexity=500, attributes=500, is_test=True),
            class_measures("Visitor", complexity=400, attributes=2, is_dispatch=True),
            class_measures("Record", complexity=2, attributes=300, is_data=True),
        ]
        aggregates = category("design", [summary(classes=classes)]).aggregates
        self.assertEqual(aggregates["classes"], 4)
        self.assertEqual(aggregates["complexity_max"], 80)
        self.assertEqual(aggregates["attributes_max"], 20)
        self.assertEqual(aggregates["complexity_over"], Share(1, 2))
        self.assertEqual(aggregates["attributes_over"], Share(1, 2))

    def test_design_counts_contracts_and_chains(self) -> None:
        file = summary(
            classes=[class_measures(complexity=9, attributes=3)],
            violations={"FUR402": 2, "FUR403": 3, "FUR404": 1},
        )
        result = category("design", [file])
        self.assertEqual(result.aggregates["contracts"], 2)
        self.assertEqual(result.aggregates["chains"], 3)
        self.assertEqual(
            result.worst,
            (
                {
                    "path": "a.py",
                    "violations": 6,
                    "max_complexity": 9,
                    "max_attributes": 3,
                    "contracts": 2,
                    "chains": 3,
                },
            ),
        )

    def test_violations_per_rule(self) -> None:
        files = [
            summary(
                "a.py",
                violations={"FUR403": 2},
                suppressed={"FUR403": 3},
                fixable={"FUR403": 1},
            ),
            summary("b.py", violations={"FUR403": 1}),
            summary("c.py"),
        ]
        row = next(
            item for item in category("design", files).rules if item.code == "FUR403"
        )
        self.assertEqual(row.name, "demeter-chain")
        self.assertEqual(
            (row.violations, row.files, row.suppressed, row.fixable), (3, 2, 3, 1)
        )

    def test_rule_with_no_violation_is_listed_at_zero(self) -> None:
        codes = [row.code for row in category("size", [summary()]).rules]
        self.assertEqual(codes, ["FUR101", "FUR102"])


class SummaryTest(unittest.TestCase):
    def test_cards(self) -> None:
        files = [
            summary(
                "a.py",
                lines=30,
                code_lines=20,
                functions=[function(), function()],
                classes=[class_measures()],
                violations={"FUR101": 1, "FUR001": 2},
                suppressed={"FUR403": 4},
                fixable={"FUR001": 2},
            ),
            summary("b.py", lines=10, code_lines=5),
        ]
        cards = model_of(files).summary
        self.assertEqual((cards.files, cards.files_in_error), (2, 0))
        self.assertEqual((cards.lines, cards.code_lines), (40, 25))
        self.assertEqual((cards.functions, cards.classes), (2, 1))
        self.assertEqual(cards.violations, 3)
        self.assertEqual(cards.density, 120.0)
        self.assertEqual(
            (cards.suppressed, cards.unused_foqa, cards.fixable), (4, 2, 2)
        )

    def test_density_without_code(self) -> None:
        self.assertIsNone(model_of([summary(code_lines=0)]).summary.density)

    def test_a_file_in_error_is_left_out_of_the_aggregates(self) -> None:
        model = model_of(
            [summary("ok.py", violations={"FUR403": 1}), failed(violations=3)]
        )
        self.assertEqual((model.summary.files, model.summary.files_in_error), (1, 1))
        self.assertEqual(model.summary.violations, 1)
        design = next(item for item in model.categories if item.key == "design")
        self.assertEqual(design.share, Share(1, 1))

    def test_every_diagnostic_still_decides_the_exit_code(self) -> None:
        model = model_of(
            [summary("ok.py", violations={"FUR403": 1}), failed(violations=3)]
        )
        self.assertEqual(model.total_violations, 4)

    def test_analysis_errors_are_complete_and_sorted(self) -> None:
        results = [failed(f"{index:02}.py") for index in range(30, 0, -1)]
        model = model_of(results)
        paths = [error.path for error in model.errors]
        self.assertEqual(len(paths), 30)
        self.assertEqual(paths, sorted(paths))

    def test_an_internal_error_is_listed_and_counted(self) -> None:
        failure = FileFailure(ROOT / "boom.py", "RecursionError: too deep")
        model = model_of([summary()], failures=[failure])
        self.assertEqual(model.summary.files_in_error, 1)
        error = model.errors[0]
        self.assertEqual(Path(error.path).name, "boom.py")
        self.assertIsNone(error.code)
        self.assertIsNone(error.location)
        self.assertEqual(error.message, "RecursionError: too deep")

    def test_header(self) -> None:
        timing = Timing(FIXED_TIME, FIXED_TIME + timedelta(seconds=2.5))
        header = model_of(config_file=ROOT / "furryp.json", timing=timing).header
        self.assertEqual(header.title, "furryp — audit")
        self.assertEqual(header.generated_at, "2026-01-02T03:04:05+00:00")
        self.assertEqual(header.duration, 2.5)
        self.assertEqual(header.active_rules, 11)
        self.assertEqual(header.project_root, str(ROOT))
        self.assertEqual(header.config_file, str(ROOT / "furryp.json"))

    def test_header_without_configuration_file(self) -> None:
        self.assertIsNone(model_of().header.config_file)

    def test_a_clock_that_goes_back_gives_no_negative_duration(self) -> None:
        timing = Timing(FIXED_TIME, FIXED_TIME - timedelta(seconds=5))
        self.assertEqual(model_of(timing=timing).header.duration, 0.0)

    def test_active_rules_follow_the_selection_and_keep_fur000(self) -> None:
        header = model_of(data={"select": ["FUR101"]}).header
        self.assertEqual(header.active_rules, 2)

    def test_configuration_is_reloadable_json(self) -> None:
        loaded = json.loads(model_of(data={"report": {"top-n": 3}}).configuration)
        self.assertEqual(loaded["report"]["top-n"], 3)
        self.assertIn("function-too-long", loaded["rules"])

    def test_the_order_of_the_analysis_does_not_matter(self) -> None:
        files = [summary("b.py", violations={"FUR403": 1}), summary("a.py")]
        first = model_of(files)
        second = model_of(list(reversed(files)))
        self.assertEqual(first, second)
