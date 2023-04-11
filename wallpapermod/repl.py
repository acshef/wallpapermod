import code, csv, datetime, logging

PER_PAGE = 100

if __name__ == "__main__":
    from wallpapermod import _BaseApp

    logging.basicConfig(format="%(asctime)s - %(levelname)-8s - %(message)s", level=logging.INFO)
    log = logging.getLogger()

    app = _BaseApp(log)
    code.interact(banner="", local=locals())

    # with open("bans.txt", "wb") as file:
    #     after = None
    #     i = 1
    #     while True:
    #         params = {}
    #         if after:
    #             params["after"] = after
    #             params["count"] = PER_PAGE

    #         for ban in app.subreddit.banned(limit=PER_PAGE, params=params):
    #             row = list[str](
    #                 [
    #                     ban.name,
    #                     datetime.datetime.fromtimestamp(ban.date).isoformat(),
    #                     ban.days_left or "Permanent",
    #                     ban.note,
    #                 ]
    #             )
    #             app.log.info(f"{i}: " + ", ".join(row))
    #             i += 1
    #             for i, x in enumerate(row):
    #                 file.write(str(x).encode("utf-8"))
    #                 if i == len(row) - 1:
    #                     file.write("\n".encode("utf-8"))
    #                 else:
    #                     file.write(", ".encode("utf-8"))
    #             after = ban.rel_id
