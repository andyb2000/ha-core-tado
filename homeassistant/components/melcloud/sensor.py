"""Support for MelCloud device sensors."""

from __future__ import annotations

from collections.abc import Callable
import dataclasses
from typing import Any

from pymelcloud import DEVICE_TYPE_ATA, DEVICE_TYPE_ATW
from pymelcloud.atw_device import Zone

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback


@dataclasses.dataclass(frozen=True, kw_only=True)
class MelcloudSensorEntityDescription(SensorEntityDescription):
    """Describes Melcloud sensor entity."""

    value_fn: Callable[[Any], float]
    enabled: Callable[[Any], bool]


ATA_SENSORS: tuple[MelcloudSensorEntityDescription, ...] = (
    MelcloudSensorEntityDescription(
        key="room_temperature",
        translation_key="room_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: x.device.room_temperature,
        enabled=lambda x: True,
    ),
    MelcloudSensorEntityDescription(
        key="energy",
        translation_key="energy_consumed",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda x: x.device.total_energy_consumed,
        enabled=lambda x: x.device.has_energy_consumed_meter,
    ),
)
ATW_SENSORS: tuple[MelcloudSensorEntityDescription, ...] = (
    MelcloudSensorEntityDescription(
        key="outside_temperature",
        translation_key="outside_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: x.device.outside_temperature,
        enabled=lambda x: True,
    ),
    MelcloudSensorEntityDescription(
        key="tank_temperature",
        translation_key="tank_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: x.device.tank_temperature,
        enabled=lambda x: True,
    ),
)
ATW_ZONE_SENSORS: tuple[MelcloudSensorEntityDescription, ...] = (
    MelcloudSensorEntityDescription(
        key="room_temperature",
        translation_key="room_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda zone: zone.room_temperature,
        enabled=lambda x: True,
    ),
    MelcloudSensorEntityDescription(
        key="flow_temperature",
        translation_key="flow_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda zone: zone.flow_temperature,
        enabled=lambda x: True,
    ),
    MelcloudSensorEntityDescription(
        key="return_temperature",
        translation_key="return_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda zone: zone.return_temperature,
        enabled=lambda x: True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up MELCloud device sensors based on config_entry."""
    coordinator = entry.runtime_data
    mel_devices = coordinator.data
    entities: list[MelDeviceSensor] = [
        MelDeviceSensor(mel_device, description, coordinator)
        for description in ATA_SENSORS
        for mel_device in mel_devices.get(DEVICE_TYPE_ATA, [])
        if description.enabled(mel_device)
    ] + [
        MelDeviceSensor(mel_device, description, coordinator)
        for description in ATW_SENSORS
        for mel_device in mel_devices.get(DEVICE_TYPE_ATW, [])
        if description.enabled(mel_device)
    ]
    entities.extend(
        [
            AtwZoneSensor(mel_device, zone, description, coordinator)
            for mel_device in mel_devices.get(DEVICE_TYPE_ATW, [])
            for zone in mel_device.device.zones
            for description in ATW_ZONE_SENSORS
            if description.enabled(zone)
        ]
    )
    async_add_entities(entities, True)


class MelDeviceSensor(SensorEntity):
    """Representation of a Sensor."""

    entity_description: MelcloudSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        api,
        description: MelcloudSensorEntityDescription,
        coordinator,
    ) -> None:
        """Initialize the sensor."""
        self._api = api
        self.entity_description = description
        self.coordinator = coordinator
        self._attr_unique_id = f"{api.device.serial}-{api.device.mac}-{description.key}"
        self._attr_device_info = api.device_info
        self._attr_should_poll = False

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self._api)

    async def async_added_to_hass(self) -> None:
        """Register for coordinator updates."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )


class AtwZoneSensor(MelDeviceSensor):
    """Air-to-Air device sensor."""

    def __init__(
        self,
        api,
        zone: Zone,
        description: MelcloudSensorEntityDescription,
        coordinator,
    ) -> None:
        """Initialize the sensor."""
        if zone.zone_index != 1:
            description = dataclasses.replace(
                description,
                key=f"{description.key}-zone-{zone.zone_index}",
            )
        super().__init__(api, description, coordinator)

        self._attr_device_info = api.zone_device_info(zone)
        self._zone = zone

    @property
    def native_value(self) -> float | None:
        """Return zone based state."""
        return self.entity_description.value_fn(self._zone)
