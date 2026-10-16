import unittest

import pandas as pd
import pm4py

from python_analysis.functions import (
    bottleneck_analysis,
    compare_declarations,
    conformance_analysis,
    process_durations,
    rejection_analysis,
    rejection_triples,
    rejections_without_employee_followup,
    unexpected_behavior,
)


def event_log(rows):
    log = pd.DataFrame(rows, columns=["case:concept:name", "concept:name", "day"])
    log["time:timestamp"] = pd.Timestamp("2025-01-01", tz="UTC") + pd.to_timedelta(log.pop("day"), unit="D")
    return log


class QuestionAnalysisTests(unittest.TestCase):
    def test_rejections_without_employee_followup_immediate_and_entity_specific(self):
        rejected = "Declaration REJECTED by SUPERVISOR"
        employee = "Declaration REJECTED by EMPLOYEE"
        permit = "Permit REJECTED by DIRECTOR"
        log = event_log([
            ("ok", rejected, 0), ("ok", "Start trip", 1),
            ("ok", "End trip", 2), ("ok", employee, 3),
            ("late", employee, 2),
            ("late", "Declaration SUBMITTED by EMPLOYEE", 1),
            ("late", rejected, 0),
            ("end", rejected, 0),
            ("next-case", employee, 0),
            ("wrong-entity", permit, 0), ("wrong-entity", employee, 1),
            ("permit-ok", permit, 0), ("permit-ok", "End trip", 1),
            ("permit-ok", "Permit REJECTED by EMPLOYEE", 2),
            ("multiple", rejected, 0), ("multiple", rejected, 1),
            ("multiple", "Declaration SAVED by EMPLOYEE", 2),
            ("unknown", "Permit REJECTED by MISSING", 0),
        ])
        original = log.copy(deep=True)
        result = rejections_without_employee_followup(log)
        self.assertEqual(result["cases"]["Treffer"].to_dict(), {
            "end": 1, "late": 1, "multiple": 2, "unknown": 1, "wrong-entity": 1,
        })
        self.assertEqual(len(result["events"]), 6)
        details = result["events"].set_index("case:concept:name")
        self.assertEqual(details.loc["end", "Nachaktivitaet"], "<Trace-Ende>")
        self.assertEqual(details.loc["late", "Nachaktivitaet"], "D10")
        self.assertEqual(details.loc["wrong-entity", "Erwartet"], "P5❌0")
        self.assertEqual(details.loc["wrong-entity", "Nachaktivitaet"], "D5❌0")
        pd.testing.assert_frame_equal(log, original)

    def test_rejections_without_employee_followup_ties_and_empty_matches(self):
        log = event_log([
            ("a", "Permit REJECTED by DIRECTOR", 0),
            ("a", "Permit REJECTED by EMPLOYEE", 0),
        ]).rename(columns={"case:concept:name": "case:id"})
        result = rejections_without_employee_followup(log, case_id="case:id")
        self.assertTrue(result["cases"].empty)
        self.assertTrue(result["events"].empty)
        self.assertEqual(result["cases"].index.name, "case:id")
        for activity in ("Start trip", "Declaration SUBMITTED by EMPLOYEE"):
            result = rejections_without_employee_followup(event_log([("a", activity, 0)]))
            self.assertTrue(result["cases"].empty)
            self.assertTrue(result["events"].empty)

    def test_rejection_triples_counts_boundaries_and_formatting(self):
        submitted = "Declaration SUBMITTED by EMPLOYEE"
        rejected = "Declaration REJECTED by EMPLOYEE"
        log = event_log([
            ("a", submitted, 4), ("a", rejected, 3),
            ("a", submitted, 2), ("a", rejected, 1), ("a", submitted, 0),
            ("b", submitted, 0), ("b", rejected, 1), ("b", submitted, 2),
            ("c", rejected, 0),
            ("d", "Permit REJECTED by SUPERVISOR", 0),
            ("e", "Declaration FINAL_APPROVED by DIRECTOR", 0),
        ])
        original = log.copy(deep=True)
        styled = rejection_triples(log).set_uuid("triples")
        table = styled.data
        self.assertEqual(list(table.columns), ["Triple", "Anzahl", "Traces", "Prozent"])
        self.assertEqual(table["Triple"].tolist(), [
            "D10 → D5❌0 → D10",
            "<Trace-Anfang> → D5❌0 → <Trace-Ende>",
            "<Trace-Anfang> → P5❌5 → <Trace-Ende>",
        ])
        self.assertEqual(table["Anzahl"].tolist(), [3, 1, 1])
        self.assertEqual(table["Traces"].tolist(), [2, 1, 1])
        self.assertEqual(table["Prozent"].tolist(), [75, 25, 100])
        html = styled.to_html()
        css = html.split("</style>")[0]
        self.assertIn("border-top: 3px solid #888;", css)
        self.assertIn("#T_triples_row2_col0", css)
        self.assertNotIn("#T_triples_row0_col0", css)
        self.assertNotIn("#T_triples_row1_col0", css)
        self.assertIn("&lt;Trace-Anfang&gt;", html)
        self.assertIn("75.00 %", html)
        pd.testing.assert_frame_equal(log, original)

    def test_rejection_triples_ties_custom_case_id_and_no_rejections(self):
        log = event_log([
            ("a", "Declaration SUBMITTED by EMPLOYEE", 0),
            ("a", "Declaration REJECTED by SUPERVISOR", 0),
            ("a", "Declaration REJECTED by EMPLOYEE", 0),
        ]).rename(columns={"case:concept:name": "case:id"})
        table = rejection_triples(log, case_id="case:id").data
        self.assertEqual(set(table["Triple"]), {
            "D10 → D5❌5 → D5❌0",
            "D5❌5 → D5❌0 → <Trace-Ende>",
        })
        self.assertTrue(table["Prozent"].eq(100).all())
        styled = rejection_triples(log.iloc[:1], case_id="case:id")
        self.assertTrue(styled.data.empty)
        self.assertIn("<table", styled.to_html())

    def test_duration_sorting_groups_and_single_event_cases(self):
        log = event_log([("b", "B", 5), ("a", "A", 0), ("b", "A", 1)])
        log["budget"] = ["x", "y", "x"]
        original = log.copy(deep=True)
        result = process_durations(log, group_by="budget")
        self.assertEqual(result["cases"].loc["b", "duration_days"], 4)
        self.assertEqual(result["cases"].loc["a", "duration_days"], 0)
        self.assertEqual(result["summary"].iloc[0]["median_days"], 2)
        self.assertEqual(result["by_group"].loc["x", "cases"], 1)
        self.assertEqual(result["by_start_month"].iloc[0]["cases"], 2)
        pd.testing.assert_frame_equal(log, original)

    def test_invalid_inputs_are_not_silently_dropped(self):
        log = event_log([("a", "A", 0), ("a", "B", 1)])
        with self.assertRaises(ValueError):
            process_durations(log.iloc[:0])
        with self.assertRaises(KeyError):
            process_durations(log.drop(columns="concept:name"))
        with self.assertRaises(ValueError):
            process_durations(log.assign(**{"time:timestamp": pd.NaT}))
        with self.assertRaises(ValueError):
            process_durations(log.assign(budget=["x", "y"]), group_by="budget")
        with self.assertRaises(ValueError):
            rejection_analysis(log)

    def test_bottlenecks_do_not_cross_case_boundaries(self):
        log = event_log([("a", "A", 0), ("b", "B", 30), ("a", "B", 2), ("c", "A", 1), ("c", "B", 5)])
        result = bottleneck_analysis(log)
        pair = result["transitions"].loc[("A", "B")]
        self.assertEqual(len(result["intervals"]), 2)
        self.assertEqual(pair["occurrences"], 2)
        self.assertEqual(pair["median_days"], 3)
        self.assertEqual(pair["total_days"], 6)
        self.assertAlmostEqual(pair["case_share"], 2 / 3)
        self.assertTrue(bottleneck_analysis(log, min_occurrences=3)["transitions"].empty)
        single = event_log([("a", "A", 0)])
        self.assertTrue(bottleneck_analysis(single)["transitions"].empty)

    def test_rejections_count_cases_and_later_decisions(self):
        log = event_log([
            ("a", "Declaration REJECTED by EMPLOYEE", 1),
            ("a", "Declaration REJECTED by SUPERVISOR", 2),
            ("a", "Declaration FINAL_APPROVED by DIRECTOR", 3),
            ("b", "Declaration FINAL_APPROVED by DIRECTOR", 0),
            ("b", "Declaration REJECTED by EMPLOYEE", 1),
            ("c", "Declaration SUBMITTED by EMPLOYEE", 1),
            ("d", "Permit REJECTED by EMPLOYEE", 1),
        ])
        result = rejection_analysis(log)
        summary = result["summary"].iloc[0]
        self.assertEqual(summary["cases"], 3)
        self.assertEqual(summary["rejection_events"], 3)
        self.assertEqual(summary["rejected_cases"], 2)
        self.assertEqual(summary["final_approval_after_last_rejection"], 1)
        self.assertEqual(summary["last_entity_event_rejected"], 1)
        self.assertAlmostEqual(summary["rejected_share"], 2 / 3)
        self.assertTrue(result["cases"].loc["a", "final_approval_after_last_rejection"])
        self.assertFalse(result["cases"].loc["b", "final_approval_after_last_rejection"])
        self.assertEqual(rejection_analysis(log, entity="Permit")["summary"].iloc[0]["cases"], 1)

    def test_precedence_missing_late_ties_and_ineligible_cases(self):
        log = event_log([
            ("ok", "approve", 0), ("ok", "trip", 1),
            ("missing", "trip", 1),
            ("late", "trip", 1), ("late", "approve", 2),
            ("tie", "approve", 1), ("tie", "trip", 1),
            ("ineligible", "approve", 1),
        ])
        result = unexpected_behavior(log, {"approval": ({"approve"}, {"trip"})})
        summary = result["summary"].loc["approval"]
        self.assertEqual(summary["eligible_cases"], 4)
        self.assertEqual(summary["violations"], 2)
        self.assertEqual(summary["violation_share"], 0.5)
        self.assertEqual(summary["same_timestamp"], 1)
        statuses = result["cases"].set_index("case:concept:name")["status"]
        self.assertEqual(statuses["ok"], "ok")
        self.assertEqual(statuses["missing"], "missing_required")
        self.assertEqual(statuses["late"], "required_after_trigger")
        self.assertEqual(statuses["ineligible"], "no_trigger")
        no_trigger = unexpected_behavior(log, {"absent": ({"approve"}, {"absent"})})
        self.assertTrue(pd.isna(no_trigger["summary"].iloc[0]["violation_share"]))

    def test_conformance_preserves_case_mapping_and_unknown_activities(self):
        training = event_log([("train", "A", 0), ("train", "B", 1)])
        model = pm4py.discover_petri_net_inductive(training)
        log = event_log([
            ("z-fit", "A", 0), ("z-fit", "B", 1),
            ("a-unknown", "A", 0), ("a-unknown", "X", 1), ("a-unknown", "B", 2),
            ("m-missing", "A", 0),
        ])
        result = conformance_analysis(log, model)
        cases = result["cases"]
        self.assertTrue(cases.loc["z-fit", "trace_is_fit"])
        self.assertFalse(cases.loc["a-unknown", "trace_is_fit"])
        self.assertFalse(cases.loc["m-missing", "trace_is_fit"])
        self.assertEqual(cases.loc["a-unknown", "unknown_activities"], ("X",))
        self.assertEqual(result["summary"].iloc[0]["fitting_cases"], 1)
        self.assertEqual(result["patterns"]["non_fitting_cases"].sum(), 2)
        renamed = log.rename(columns={"case:concept:name": "case:id"})
        self.assertEqual(
            conformance_analysis(renamed, model, case_id="case:id")["summary"].iloc[0]["cases"], 3
        )

    def test_comparison_separates_full_and_declaration_durations(self):
        domestic = event_log([
            ("shared-id", "Declaration SUBMITTED by EMPLOYEE", 0),
            ("shared-id", "Declaration FINAL_APPROVED by DIRECTOR", 2),
        ])
        international = event_log([
            ("shared-id", "Permit FINAL_APPROVED by DIRECTOR", 0),
            ("shared-id", "Declaration SUBMITTED by EMPLOYEE", 10),
            ("shared-id", "Declaration REJECTED by EMPLOYEE", 14),
            ("no-declaration", "Permit FINAL_APPROVED by DIRECTOR", 0),
        ])
        result = compare_declarations(domestic, international)
        overview = result["overview"]
        self.assertEqual(overview.loc["full_median_days", "international"], 7)
        self.assertEqual(overview.loc["declaration_median_days", "international"], 4)
        self.assertEqual(overview.loc["cases_without_declaration", "international"], 1)
        self.assertEqual(overview.loc["rejected_share", "international"], 1)
        self.assertEqual(overview.loc["rejected_share", "domestic"], 0)
        shares = result["declaration_activity_shares"]
        self.assertEqual(shares.loc["Declaration REJECTED by EMPLOYEE", "international"], 1)
        self.assertEqual(shares.loc["Declaration REJECTED by EMPLOYEE", "domestic"], 0)


if __name__ == "__main__":
    unittest.main()
