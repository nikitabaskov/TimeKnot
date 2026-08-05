/**
 * A relay from IPv6 to the Telegram Bot API.
 *
 * api.telegram.org publishes no AAAA record, so a host without IPv4 cannot
 * reach it at all. Cloudflare is dual-stack on both sides: the bot connects to
 * this Worker over IPv6, the Worker connects onward over IPv4.
 *
 * Requests keep their shape — /bot<token>/<method> and /file/bot<token>/<path>
 * are passed through untouched, which is what lets aiogram treat this as an
 * ordinary Bot API server.
 */

const TELEGRAM = "https://api.telegram.org";

// A relay anyone can use is a relay someone else will use. The bot token is
// already in the path, so matching it against the configured one costs nothing
// and pins this Worker to a single bot.
const TOKEN_IN_PATH = /^\/(?:file\/)?bot([^/]+)\//;

export default {
  async fetch(request, env) {
    if (request.method !== "POST" && request.method !== "GET") {
      return new Response("Method not allowed\n", { status: 405 });
    }

    const url = new URL(request.url);
    const match = TOKEN_IN_PATH.exec(url.pathname);
    if (!match || match[1] !== env.TELEGRAM_BOT_TOKEN) {
      // Deliberately vague: an error page is not the place to confirm which
      // half of the guess was right.
      return new Response("Not found\n", { status: 404 });
    }

    // Host must come from the target, not from whatever the client sent, and
    // Cloudflare's own hop headers mean nothing to Telegram.
    const headers = new Headers(request.headers);
    for (const header of ["host", "cf-connecting-ip", "cf-ray", "x-forwarded-for"]) {
      headers.delete(header);
    }

    return fetch(TELEGRAM + url.pathname + url.search, {
      method: request.method,
      headers,
      body: request.body,
    });
  },
};
