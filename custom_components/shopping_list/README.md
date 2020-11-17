[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
# Custom Shopping List with Bring integration.

A custom implementation of Home Assistant's Shopping List that synchronises with Bring Shopping List (https://getbring.com/#!/app). This overrides the core implementation of Shopping List and thus is accessible in Home Assistant from the sidebar or through the [Shopping List card](https://www.home-assistant.io/lovelace/shopping-list/)

## Installation

### HACS

Add the repository url to your custom repositories in HACS: https://github.com/vlebourl/custom_shopping_list
and install `Shopping List`.

### Manual

Download the [zip](https://github.com/vlebourl/custom_shopping_list/archive/main.zip) and extract it. Copy the folder `shopping_list` to your `custom_components` folder.

## Usage

To use it, add the following to your configuration.yaml:

```yaml
shopping_list:
  bring_username: 'username'
  bring_password: 'password'
  bring_language: 'en-EN'
```

Full list of supported language isn't known, language should follow the `locale` format, such as `de-DE`, `fr-FR`, `ch-FR`, etc.
