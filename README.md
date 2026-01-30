# The Keys Integration

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![hacs][hacsbadge]][hacs]
![Project Maintenance][maintenance-shield]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

[![Community Forum][forum-shield]][forum]

_Integration to integrate with [KevinBonnoron/the_keys][KevinBonnoron/the_keys]._

**This integration will set up the following platforms.**

Platform | Description
-- | --
`lock` | Allow to change and see the lock status.
`sensor` | Show accurate battery percentage (calibrated from real data).
`button` | Buttons for calibrate and sync operations (visible in Controls dashboard).

**Buttons:**
- **Calibrate** - Calibrate the lock mechanism
- **Sync** - Sync lock state with the cloud

**Custom Services:**

Service | Description
-- | --
`the_keys.calibrate` | Calibrate the lock mechanism (for automations/scripts)
`the_keys.sync` | Sync lock state with the cloud (for automations/scripts)

*Note: Both button entities (for manual use in UI) and services (for automations) are available for calibrate and sync operations.*

## Installation

1. Using the tool of choice open the directory (folder) for your HA configuration (where you find `configuration.yaml`).
2. If you do not have a `custom_components` directory (folder) there, you need to create it.
3. In the `custom_components` directory (folder) create a new folder called `the_keys`.
4. Download _all_ the files from the `custom_components/the_keys/` directory (folder) in this repository.
5. Place the files you downloaded in the new directory (folder) you created.
6. Restart Home Assistant
7. In the HA UI go to "Configuration" -> "Integrations" click "+" and search for "The Keys"

## Configuration is done in the UI

### Configuration Options

- **Username**: Your phone number in international format (e.g., +33...)
- **Password**: Your The Keys account password
- **Gateway IP** (optional): Manual gateway IP/hostname if auto-discovery fails
- **Scan Interval**: How often to poll for updates (minimum 10 seconds, default 60 seconds)

### Recent Improvements

**v1.2.0 (2026-01-30)**
- ✓ **Battery Accuracy Fix**: Battery percentages now accurately reflect real values (±1% accuracy)
  - Previous version overestimated by 5-9%
  - Uses linear regression calibrated from real device data
- ✓ **Gateway Rate Limiting**: Prevents timeouts and gateway overload
  - Heavy operations (open/close/calibrate/status): 8 second delay
  - Light operations (status/list/sync): 2 second delay
  - Per-gateway instance rate limiting

<!---->

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

***

[KevinBonnoron/the_keys]: https://github.com/KevinBonnoron/the_keys
[buymecoffee]: https://www.buymeacoffee.com/kevinbonnoron
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge
[commits-shield]: https://img.shields.io/github/commit-activity/y/KevinBonnoron/the_keys.svg?style=for-the-badge
[commits]: https://github.com/KevinBonnoron/the_keys/commits/main
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
[exampleimg]: example.png
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/KevinBonnoron/the_keys.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-Kevin%20Bonnoron%20%40KevinBonnoron-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/KevinBonnoron/the_keys.svg?style=for-the-badge
[releases]: https://github.com/KevinBonnoron/the_keys/releases
