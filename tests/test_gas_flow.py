from __future__ import annotations

import pytest

from analysis.gas_flow import (
    GasFlowConfig,
    GasFlowProcessor,
    GasSensorChannelConfig,
    flow_wiring_order,
    validate_flow_wiring,
)


def test_voltage_divider_high_and_low_side_formulas():
    high = GasFlowProcessor(GasFlowConfig(
        voltage_to_resistance=True,
        voltage_field="voltage",
        supply_voltage_v=5.0,
        reference_resistance_ohm=10_000.0,
        divider_topology="sensor_high",
    ))
    low = GasFlowProcessor(GasFlowConfig(
        voltage_to_resistance=True,
        voltage_field="voltage",
        supply_voltage_v=5.0,
        reference_resistance_ohm=10_000.0,
        divider_topology="sensor_low",
    ))
    assert high.process_record({"voltage": 1.0})["resistance_ohm"] == pytest.approx(40_000)
    assert low.process_record({"voltage": 1.0})["resistance_ohm"] == pytest.approx(2_500)


def test_flow_auto_detects_daq_voltage_and_preserves_invalid_rows():
    processor = GasFlowProcessor(GasFlowConfig(voltage_to_resistance=True))
    rows = processor.process_records([
        {"elapsed_s": 0.0, "ai0_voltage_v": 2.5, "event": ""},
        {"elapsed_s": 0.1, "ai0_voltage_v": None, "event": "gas_on"},
        {"elapsed_s": 0.2, "ai0_voltage_v": 5.0, "event": ""},
    ])
    assert len(rows) == 3
    assert rows[0]["resistance_ohm"] == pytest.approx(10_000)
    assert rows[1]["resistance_ohm"] is None and rows[1]["event"] == "gas_on"
    assert rows[2]["resistance_ohm"] is None


def test_moving_average_keeps_state_across_controller_batches():
    processor = GasFlowProcessor(GasFlowConfig(
        smoothing=True,
        smoothing_field="resistance",
        smoothing_window=3,
    ))
    first = processor.process_records([{"resistance": 3.0}, {"resistance": 6.0}])
    second = processor.process_records([{"resistance": None}, {"resistance": 12.0}])
    assert [row["resistance_ma3"] for row in first] == pytest.approx([3.0, 4.5])
    assert second[0]["resistance_ma3"] is None
    assert second[1]["resistance_ma3"] == pytest.approx(7.0)


def test_combined_flow_adds_resistance_then_smooths_it():
    processor = GasFlowProcessor(GasFlowConfig(
        voltage_to_resistance=True,
        smoothing=True,
        smoothing_field="resistance_ohm",
        smoothing_window=2,
    ))
    rows = processor.process_records([
        {"voltage": 2.5},
        {"voltage": 2.0},
    ])
    assert rows[0]["resistance_ohm"] == pytest.approx(10_000)
    assert rows[1]["resistance_ohm"] == pytest.approx(15_000)
    assert rows[1]["resistance_ohm_ma2"] == pytest.approx(12_500)


def test_flow_config_round_trip_and_validation():
    config = GasFlowConfig.from_dict({
        "voltage_to_resistance": True,
        "supply_voltage_v": 3.3,
        "reference_resistance_ohm": 4700,
        "divider_topology": "sensor_low",
        "unknown": "ignored",
    })
    assert GasFlowConfig.from_dict(config.to_dict()) == config
    with pytest.raises(ValueError, match="Supply voltage"):
        GasFlowConfig(supply_voltage_v=0).validated()
    with pytest.raises(ValueError, match="window"):
        GasFlowConfig(smoothing_window=0).validated()


def test_flow_wiring_rejects_loops_and_requires_outputs():
    with pytest.raises(ValueError, match="loop"):
        validate_flow_wiring([
            ["source", "book"], ["book", "graph"],
            ["divider", "smooth"], ["smooth", "divider"],
        ])
    with pytest.raises(ValueError, match="reach"):
        validate_flow_wiring([["source", "graph"]])
    assert flow_wiring_order([
        ["source", "book"], ["book", "graph"],
        ["source", "divider"], ["divider", "smooth"],
    ]) == ("source", "book", "graph")


def test_flow_wiring_bypasses_disconnected_processors():
    config = GasFlowConfig(
        voltage_to_resistance=True,
        smoothing=True,
        voltage_field="voltage",
        smoothing_field="resistance_ohm",
    )
    processor = GasFlowProcessor(config, [["source", "book"], ["book", "graph"]])
    row = processor.process_record({"voltage": 2.5})
    assert row == {"voltage": 2.5}
    processor.configure_wiring([
        ["source", "divider"], ["divider", "book"], ["book", "graph"]
    ])
    row = processor.process_record({"voltage": 2.5})
    assert row["resistance_ohm"] == pytest.approx(10_000)
    assert not any(name.endswith("_ma5") for name in row)


def test_multiple_sensor_channels_have_independent_aliases_and_processing():
    processor = GasFlowProcessor(GasFlowConfig(sensor_channels=(
        GasSensorChannelConfig(
            source_field="ai0_voltage_v",
            alias="MQ-2 chamber A",
            voltage_to_resistance=True,
            reference_resistance_ohm=10_000,
            smoothing=True,
            smoothing_window=2,
        ),
        GasSensorChannelConfig(
            source_field="ai1_voltage_v",
            alias="MQ-135 chamber B",
            smoothing=True,
            smoothing_window=3,
        ),
    )))
    rows = processor.process_records([
        {"ai0_voltage_v": 2.5, "ai1_voltage_v": 1.0},
        {"ai0_voltage_v": 2.0, "ai1_voltage_v": 2.0},
    ])
    assert rows[0]["ai0_voltage_v"] == 2.5  # raw input is preserved
    assert rows[0]["MQ-2 chamber A resistance_ohm"] == pytest.approx(10_000)
    assert rows[1]["MQ-2 chamber A resistance_ohm_ma2"] == pytest.approx(12_500)
    assert rows[1]["MQ-135 chamber B_ma3"] == pytest.approx(1.5)


def test_sensor_channel_config_round_trip_and_unique_names():
    config = GasFlowConfig.from_dict({"sensor_channels": [
        {"source_field": "ai0_voltage_v", "alias": "Sensor A"},
        {"source_field": "ai1_voltage_v", "alias": "Sensor B", "smoothing": True},
    ]})
    assert GasFlowConfig.from_dict(config.to_dict()) == config
    assert config.sensor_channels[1].output_field == "Sensor B_ma5"
    with pytest.raises(ValueError, match="display names"):
        GasFlowConfig(sensor_channels=(
            GasSensorChannelConfig("ai0", "Same"),
            GasSensorChannelConfig("ai1", "same"),
        )).validated()
