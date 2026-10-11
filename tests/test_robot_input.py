"""제조사 단위 매핑과 선택값 보류만 검증한다. 실기 제어 시험이 아니다."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from contextweld.robot_input import build_robot_input_preview, build_work_order_input_previews, main


ROOT = Path(__file__).resolve().parents[1]
WPS = ROOT / "data/knowledge/lanl-wps-3501-reviewed.json"
PROFILE = ROOT / "configs/robot_profiles/hyundai_hi6_current_voltage.json"


class RobotInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.wps = json.loads(WPS.read_text())
        self.profile = json.loads(PROFILE.read_text())
        self.selected = {"current": "180", "voltage": "26", "travel_speed": "12"}

    def preview(self, **kwargs):
        return build_robot_input_preview(self.wps, self.profile, **kwargs)

    def test_ranges_exact_conversion_evidence_and_no_automatic_setpoint(self):
        original = deepcopy(self.wps)
        result = self.preview()
        speed = result["fields"][2]
        self.assertEqual(speed["source"]["min"], "7")
        self.assertEqual(speed["target"], {"min": "17.78", "max": "45.72", "unit": "cm/min"})
        self.assertEqual(speed["factor"], "2.54")
        self.assertEqual(speed["evidence"]["locator"]["page"], 2)
        self.assertIsNone(speed["selected"])
        self.assertIsNone(result["command_preview"])
        self.assertEqual(result["status"], "needs_setpoints")
        self.assertEqual(self.wps, original)

    def test_explicit_values_generate_only_arccond_preview(self):
        result = self.preview(setpoints=self.selected)
        self.assertEqual(result["command_preview"], "arccond D, cur=180, vol=26, spd=30.48")
        self.assertEqual(result["status"], "preview_ready")
        for flag in ("execution_authorized", "application_authorized", "hardware_verified", "delivery_requested"):
            self.assertFalse(result[flag])

    def test_boundary_values_and_decimal_input(self):
        for current, voltage, speed, expected in [(130, 24, 7, "17.78"), (250, 28, 18, "45.72"),
                                                  (180, 26, Decimal("7.0000000000000001"), "17.780000000000000254")]:
            result = self.preview(setpoints={"current": current, "voltage": voltage, "travel_speed": speed})
            self.assertEqual(result["status"], "preview_ready")
            self.assertEqual(result["fields"][2]["selected"]["target"]["value"], expected)

    def test_partial_selection_never_produces_command(self):
        result = self.preview(setpoints={"current": 180})
        self.assertEqual(result["status"], "needs_setpoints")
        self.assertEqual(result["missing_setpoints"], ["voltage", "travel_speed"])
        self.assertIsNone(result["command_preview"])

    def test_unsupported_missing_or_wire_modes_block(self):
        for modes in ({}, None, {"current": "wire_feed", "voltage": "absolute_V"},
                      {"current": "current_A", "voltage": "offset_V"}):
            self.profile["modes"] = modes
            result = self.preview(setpoints=self.selected)
            self.assertEqual(result["status"], "blocked")
            self.assertIsNone(result["command_preview"])

    def test_nonfinite_invalid_and_outside_selected_values_block(self):
        for value in ("NaN", float("inf"), True, None, "180; arcon", "1e-999999", 129, 251):
            with self.subTest(value=value):
                result = self.preview(setpoints={**self.selected, "current": value})
                self.assertEqual(result["status"], "blocked")
                self.assertIsNone(result["command_preview"])

    def test_missing_field_unit_range_and_evidence_mismatch_block(self):
        for fault in ("missing", "unit", "range", "nan", "evidence"):
            with self.subTest(fault=fault):
                self.wps = json.loads(WPS.read_text())
                fields = self.wps["pass_rows"][0]["fields"]
                if fault == "missing":
                    del fields["voltage"]
                elif fault == "unit":
                    fields["voltage"]["normalized"]["unit"] = "%"
                elif fault == "range":
                    fields["voltage"]["normalized"]["min"] = 99
                elif fault == "nan":
                    fields["voltage"]["normalized"]["min"] = "NaN"
                else:
                    fields["voltage"]["evidence"]["revision"] = "2"
                result = self.preview(setpoints=self.selected)
                self.assertEqual(result["status"], "blocked")
                self.assertIsNone(result["command_preview"])

    def test_controller_speed_bounds_and_unknown_keys_block(self):
        self.wps["pass_rows"][0]["fields"]["travel_speed"]["normalized"]["max"] = 500
        self.assertEqual(self.preview(setpoints=self.selected)["status"], "blocked")
        self.wps = json.loads(WPS.read_text())
        self.assertEqual(self.preview(setpoints={**self.selected, "job": 1})["status"], "blocked")

    def test_unknown_manufacturer_and_duplicate_or_missing_row_block(self):
        self.profile["manufacturer"] = "Doosan"
        self.assertEqual(self.preview(setpoints=self.selected)["status"], "blocked")
        self.profile = json.loads(PROFILE.read_text())
        self.assertEqual(self.preview(row_id="missing", setpoints=self.selected)["status"], "blocked")
        self.wps["pass_rows"].append(deepcopy(self.wps["pass_rows"][0]))
        self.assertEqual(self.preview(setpoints=self.selected)["status"], "blocked")

    def test_cli_writes_json_with_same_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "preview.json"
            code = main(["--wps", str(WPS), "--profile", str(PROFILE), "--current", "180",
                         "--voltage", "26", "--travel-speed", "12", "--output", str(output)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.read_text())["command_preview"],
                             "arccond D, cur=180, vol=26, spd=30.48")


class WorkOrderRobotInputTests(unittest.TestCase):
    def setUp(self):
        self.wps = json.loads(WPS.read_text())
        self.orders = json.loads((ROOT / "configs/document_demo/work_orders.json").read_text())
        self.recipes = json.loads((ROOT / "configs/document_demo/weld_recipes.json").read_text())
        self.profiles = {"hyundai": json.loads(PROFILE.read_text()), "doosan": json.loads(
            (ROOT / "configs/robot_profiles/doosan_drl_analog.json").read_text())}

    def preview(self):
        return build_work_order_input_previews(self.wps, self.orders, self.recipes, self.profiles, order_id="WO-DEMO-015")

    def test_explicit_work_recipe_autofill_two_manufacturers(self):
        original = deepcopy(self.recipes)
        result = self.preview()
        self.assertEqual(result["status"], "preview_ready")
        self.assertEqual(result["recipe_id"], "RECIPE-DEMO-015")
        self.assertEqual(result["selection_origin"], "work_order_recipe")
        self.assertEqual(result["previews"]["hyundai"]["command_preview"], "arccond D, cur=180, vol=26, spd=25.4")
        doosan = result["previews"]["doosan"]
        self.assertEqual(doosan["command_preview"], "app_weld_set_weld_cond_analog(flag_dry_run=1, v_target=26, f_target=6, vel_target=4.233333, vel_min=4.233333, vel_max=4.233333)")
        speed, wire = doosan["fields"][2:4]
        self.assertEqual(speed["target"], {"min": "2.963333", "max": "7.62", "unit": "mm/s"})
        self.assertEqual((speed["factor"], speed["divisor"], speed["precision"], speed["rounding"]),
                         ("25.4", "60", 6, "ROUND_HALF_UP"))
        self.assertTrue(doosan["fields"][0]["ref_only"])
        self.assertIsNone(doosan["fields"][0]["robot_field"])
        self.assertEqual(wire["source"]["min"], wire["source"]["max"])
        self.assertEqual(wire["evidence"]["document_id"], "DEMO-WELD-RECIPES")
        self.assertEqual(speed["evidence"]["document_id"], "lanl-wps-3501")
        self.assertEqual(speed["selection_evidence"]["document_id"], "DEMO-WELD-RECIPES")
        self.assertFalse(doosan["execution_authorized"])
        self.assertEqual(self.recipes, original)

    def test_current_does_not_convert_to_wire_feed(self):
        self.recipes["recipes"][0]["setpoints"]["current"]["value"] = "220"
        result = self.preview()["previews"]["doosan"]
        self.assertEqual(result["command_parameters"]["f_target"], "6")
        self.assertNotIn("220", result["command_preview"])

    def test_common_spec_is_shared_manufacturer_input_with_scenario_origin(self):
        result = self.preview()
        common = result["common_spec"]
        self.assertEqual(common["target"], {"part_id": "BISB30N-15", "joint_id": "JOINT-DEMO-01",
                                          "observation_ref": None, "source_kind": "fixture"})
        self.assertEqual(common["relation_origin"], "scenario_mapping")
        self.assertEqual(common["work_order"], {"order_id": "WO-DEMO-015", "revision": 1})
        self.assertEqual(common["validation"]["status"], "valid")
        self.assertFalse(common["physical_applicable"])
        self.assertFalse(common["execution_authorized"])
        for profile in result["previews"].values():
            for field in profile["fields"]:
                self.assertEqual(field["selected"]["source"]["value"], common["parameters"][field["name"]]["value"])
        self.assertEqual(common["parameters"]["voltage"]["evidence"]["document_id"], "DEMO-WELD-RECIPES")

    def test_missing_cancelled_and_conflicting_work_requirements_block_common_spec(self):
        original = deepcopy(self.orders)
        for key, value in (("part_id", None), ("joint_id", ""), ("process", None),
                           ("state", "cancelled"), ("process", "GMAW"), ("material", "A-516")):
            with self.subTest(key=key, value=value):
                self.orders = deepcopy(original)
                self.orders["orders"][0][key] = value
                result = self.preview()
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["previews"], {})
                self.assertEqual(result["common_spec"]["validation"]["status"], "blocked")
                self.assertTrue(result["common_spec"]["validation"]["issues"])

    def test_no_recipe_wrong_revision_or_wps_blocks(self):
        original = deepcopy(self.recipes)
        for fault in ("missing", "order_revision", "wps_revision", "row"):
            self.recipes = deepcopy(original)
            if fault == "missing":
                self.recipes["recipes"] = []
            elif fault == "order_revision":
                self.recipes["recipes"][0]["order_ref"]["revision"] = 2
            elif fault == "wps_revision":
                self.recipes["recipes"][0]["wps_ref"]["revision"] = "2"
            else:
                self.recipes["recipes"][0]["wps_ref"]["row_id"] = "layer-2"
            result = self.preview()
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["previews"], {})

    def test_recipe_values_validate_units_missing_nonfinite_and_wps_range(self):
        original = deepcopy(self.recipes)
        for fault in ("unit", "missing", "nan", "outside"):
            self.recipes = deepcopy(original)
            points = self.recipes["recipes"][0]["setpoints"]
            if fault == "unit":
                points["wire_feed"]["unit"] = "A"
            elif fault == "missing":
                del points["wire_feed"]
            elif fault == "nan":
                points["wire_feed"]["value"] = "NaN"
            else:
                points["travel_speed"]["value"] = "19"
            self.assertEqual(self.preview()["status"], "blocked")

    def test_doosan_direct_selection_12_and_rounding_and_mode_validation(self):
        selected = {"current": "180", "voltage": "26", "travel_speed": "12", "wire_feed": "6"}
        recipe = self.recipes["recipes"][0]
        result = build_robot_input_preview(self.wps, self.profiles["doosan"], setpoints=selected, recipe=recipe)
        self.assertEqual(result["command_parameters"]["vel_target"], "5.08")
        selected["wire_feed"] = "7"
        self.assertEqual(build_robot_input_preview(self.wps, self.profiles["doosan"], setpoints=selected, recipe=recipe)["status"], "blocked")
        selected["wire_feed"] = "6"
        self.profiles["doosan"]["modes"]["wire_feed"] = "A"
        self.assertEqual(build_robot_input_preview(self.wps, self.profiles["doosan"], setpoints=selected, recipe=recipe)["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
