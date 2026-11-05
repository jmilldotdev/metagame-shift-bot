# Metagame shift bot

Assigns a dedicated Discord role to volunteers during their scheduled shifts and posts one webhook announcement for newly assigned people. Python 3.12, standard library locally; AWS Lambda's bundled boto3 is used only for Secrets Manager and S3. No gateway, web server, pip packages, or Discord library is needed.

## Set up a local copy

1. Install Python 3.12 with timezone data available.
2. Copy `data/names.example.csv` to `data/names.csv` and replace the fictional rows with your private mapping. The first column is the volunteer's sheet name and the second their Discord handle. Keep the `Names,Discord` header. Use `no discord` for volunteers who do not use Discord.
3. Create `config.local.json` beside `config.json`:

   ```json
   {
     "sheet_url": "REPLACE_WITH_YOUR_CSV_EXPORT_URL",
     "year": 2030,
     "name_overrides": {},
     "discord_id_overrides": {}
   }
   ```

   Supply a CSV export URL accessible to the process without interactive authentication. Choose the actual event year and timezone. A publicly accessible sheet can expose personal data: obtain permission and limit its contents accordingly.
4. Follow the [Discord administrator guide](docs/discord-admin-guide.md) to install a bot, configure the dedicated role, and create a webhook.
5. Set `GUILD_ID`, `ROLE_ID`, `BOT_TOKEN`, and `WEBHOOK_URL` in your process environment before live operation. `.env.example` lists the variables; the bot does **not** load dotenv files automatically. Keep tokens and webhook URLs secret.

`config.json` supplies generic defaults. Optional `config.local.json` overlays those defaults by top-level key: an override table replaces the entire corresponding table rather than merging individual entries. `config.local.json`, `data/names.csv`, `STATE.md`, `.env`, and `.cache/` are gitignored. Keep private names, handles, IDs, sheet locations, credentials, and operational notes in these local files, not in committed examples. Existing local installations can keep their private mapping and configuration in place.

## Sheet format and identity matching

The CSV has two header rows. The first supplies a month/day in parentheses, such as `Friday (4/5)`; a day header applies to subsequent columns until the next day header. The second supplies slots such as `1pm-5pm (3)` or `9pm-12am (2)`; the optional number is not used. Remaining rows put the volunteer's name in the first column and `shift` in each assigned slot. Blank rows and a `shifts filled:` summary row are ignored. Notes are not instructions: only a cell containing `shift`, ignoring case and surrounding whitespace, assigns a shift.

Starts are inclusive and ends exclusive. A slot ending at or before its start crosses midnight into the next day. `year` and `timezone` select the local calendar; `grace_before_minutes` and `grace_after_minutes` independently extend the window and default to zero.

`name_overrides` maps an exact sheet name to a name in the mapping CSV. Parenthetical suffixes, whitespace, punctuation, accents, and case otherwise normalize away. If no normalized match exists, a conservative similarity threshold of 0.90 is used; multiple candidates are reported, never guessed. Every sheet volunteer is checked, even when off shift. Explicit `no discord` entries are reported and skipped. Any other unresolved active volunteer blocks live role mutations to avoid removing someone incorrectly.

Live mode accepts only a unique exact Discord username, global-name, or nickname match. `discord_id_overrides` maps a mapping handle to a verified Discord user ID string when needed. Never infer user IDs from numeric-looking handles. The guild-scoped identity cache is stored alongside the sheet snapshot. Each reconcile lists current guild members to find actual role holders and detect departed cached users. To refresh renamed identities, update the mapping and remove `discord_ids` from the cache, or provide verified overrides.

## Run locally

```sh
python3 -m unittest -v
python3 bot.py
python3 bot.py --at 2030-04-05T14:00:00-07:00 --current-handles example_volunteer_two
```

The CLI defaults to **dry-run**: no Discord calls, only planned handle additions/removals and an announcement preview. `--current-handles` supplies simulated current holders; without it the simulated set is empty. The example timestamp is fictional: use a date in your configured event year with an explicit UTC offset.

For a real reconcile using the configured credentials:

```sh
python3 bot.py --live
```

Live mode refuses simulated timestamps and role holders. It exits nonzero if active volunteers are unresolved (`blocked`), or if an exception occurs; successful runs exit zero. Dry-runs exit zero unless an exception occurs. Review `issues` in every result, not just the exit status.

Every invocation fetches and validates the sheet and saves a last-good snapshot in `.cache/state.json`. On a fetch or parse failure it logs a warning and uses that snapshot. Without one it fails before changing roles. Set `CACHE_FILE` to choose another local cache location. A stale snapshot has no automatic expiry: inspect warnings because schedule edits will not be reflected during an outage.

## Schedule once per minute

Use any scheduler that invokes `python3 bot.py --live` every minute, with the project as its working directory and the required environment variables available. For example, a crontab entry can use generic absolute paths:

```cron
* * * * * cd /path/to/metagame-shift-bot && /path/to/python3 bot.py --live >> /path/to/shift-bot.log 2>&1
```

Arrange credentials securely rather than placing them in the crontab or committed scripts. Prevent overlapping runs using your scheduler's single-instance option or a lock, and monitor nonzero exits and warnings. Do not run multiple live schedulers against the same role. After the last shift, allow a successful reconcile to remove the final roles before stopping the schedule.

## Optional AWS SAM deployment

Prerequisites: AWS credentials for your intended account, AWS CLI, AWS SAM CLI, Python 3.12, and permissions for Lambda, IAM roles, S3, EventBridge, CloudWatch Logs, and Secrets Manager. No AWS deployment is required for local operation.

The deployment package needs your private mapping and actual configuration. Gitignored does not mean excluded from a SAM package: protect access to deployment artifacts and never commit private files. Check your built package before uploading; do not include local memory or unrelated secrets. Configure the deployed `config.json` or packaged `config.local.json` for the actual sheet, year, timezone, and overrides.

1. Create an AWS Secrets Manager JSON secret containing `bot_token` and `webhook_url`. Use a standard Secrets Manager key; a customer-managed key requires an additional `kms:Decrypt` grant in the template.
2. Set non-secret environment values for the intended AWS region, guild, role, and full secret ARN, then deploy initially in dry-run mode:

   ```sh
   export AWS_REGION=YOUR_REGION
   export GUILD_ID=YOUR_SERVER_ID
   export ROLE_ID=YOUR_ON_SHIFT_ROLE_ID
   export SECRET_ARN=YOUR_SECRET_ARN
   sam build
   sam deploy --guided --stack-name shift-bot --region "$AWS_REGION" \
     --capabilities CAPABILITY_IAM \
     --parameter-overrides GuildId="$GUILD_ID" RoleId="$ROLE_ID" SecretArn="$SECRET_ARN" DryRun=true
   ```

3. Inspect logs using `sam logs --stack-name shift-bot --region "$AWS_REGION" --tail`. Dry-run output does not validate Discord credentials. Review mapping issues, then update the deployment to live mode:

   ```sh
   sam deploy --stack-name shift-bot --region "$AWS_REGION" --resolve-s3 \
     --capabilities CAPABILITY_IAM \
     --parameter-overrides GuildId="$GUILD_ID" RoleId="$ROLE_ID" SecretArn="$SECRET_ARN" DryRun=false
   ```

The EventBridge schedule runs every minute; Python interprets the event's local calendar in the configured timezone. Lambda concurrency is one and timeout is 55 seconds; event retries are disabled to reduce stale overlapping reconciles. Account concurrency quotas may require adjusting reserved concurrency. S3 persists the sheet snapshot and identity cache, not shift state. Logs retain 14 days. To change packaged configuration, rebuild and redeploy. After final role cleanup, disable `EveryMinute` in the template and redeploy, or delete the stack. The retained S3 bucket must be removed separately if no longer needed.

## Announcements and operational limits

The dedicated role is authoritative shift state. Every successful reconcile compares desired users to actual role holders; role PUT/DELETE calls are idempotent. The bot removes the role from anyone not scheduled, including manual holders. Newly added users are tagged in one `Now on shift: …` webhook message, with mentions restricted to exactly those users. Retained role holders are not re-announced. Manual removal during a shift causes a re-add and another announcement on the next successful run.

Role assignment and webhook delivery cannot be atomic. Failure after assignment but before delivery can lose the announcement; the next role diff prevents a duplicate role-based announcement. A partial batch announces successful additions when possible; a hard timeout can still lose the message. Discord rate limits receive bounded retries, while other failures surface to the caller. Monitor failures rather than assuming the next minute repairs missed messages.
