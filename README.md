# euronews

Downloads the EuroNews livestream so you can watch it from your favorite media player.
Once the script is started, let it run for a few seconds and then open the `euronews.ts` file in your media player, or pass it through the `--player` option. When passed via `--player`, it will be launched as soon as sufficient data as been obtained. Closing the player will stop the script.

The script prompts for a stream quality, but you can also pass it a `--quality` argument. Quality is in vertical pixels (e.g.: `--quality 720` for 720p).

The livestream is geoblocked to Europe (I think? Doesn't work in Canada), but you can provide a socks5 proxy with the `--socks5` option. Expected format is `--socks5 "socks5://user:pass@host:port"` (passed directly to the `requests` module)