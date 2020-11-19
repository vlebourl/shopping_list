[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

# Custom Shopping List with Bring integration.

A custom implementation of Home Assistant's Shopping List that synchronises with Bring Shopping List (https://getbring.com/#!/app). This overrides the core implementation of Shopping List and thus is accessible in Home Assistant from the sidebar or through the [Shopping List card](https://www.home-assistant.io/lovelace/shopping-list/)

## Installation

### HACS

Add the repository url to your custom repositories in HACS: https://github.com/vlebourl/shopping_list
and install `Shopping List`.

### Manual

Download the [zip](https://github.com/vlebourl/custom_shopping_list/archive/main.zip) and extract it. Copy the folder `shopping_list` to your `custom_components` folder.

## Usage

To use it, add the shopping list integration from the integration page and fill in your credentials, a locale, and choose the list to sync.

Full list of supported language isn't known, language should follow the `locale` format, such as `de-DE`, `fr-FR`, `ch-FR`, etc.

## Services

This integration exposes two new services: 
* `shopping_list.bring_select_list`: Select another list to sync HA with.
* `shopping_list.bring_sync`: Sync the list from Bring to HA

## Sync from Bring to HA

Items added, checked or removed from the list in HA are automatically synced with your Bring list. Items added to or removed from your Bring list needs to be synced back to HA. The Bring -> HA sync is done every time an item is modified in HA's list, but HA has no way of knowing when Bring is modified... To manually sync, use the service `shopping_list.bring_sync`. A solution can be to add an automation that syncs Bring to HA every few minutes, such as this:
```yaml
- id: 'sync_bring'
  alias: Sync Bring
  description: ''
  trigger:
  - platform: time_pattern
    hours: '*'
    minutes: /15
    seconds: '0'
  condition: []
  action:
  - service: shopping_list.bring_sync
    data: {}
  mode: single
```

## 
