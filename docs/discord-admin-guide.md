# Metagame Shift Bot: Discord admin setup

This guide is for the people who manage Metagame's Discord server. Use Discord on a computer for these steps. No programming, hosting setup, or bot token is needed from you.

**Contact:** YOUR_BOT_CONTACT. Send setup details and questions to this person by Discord DM.

## What the bot does

- Checks the volunteer schedule every minute during the event.
- Gives scheduled volunteers the **On-shift Volunteer** role and removes it when their shift ends.
- Posts a message such as **Now on shift: @volunteer** in the channel you choose. Each update groups newly on-shift people into one message and tags only those people, not the whole role or everyone.
- Reads the server's member list and member names to match volunteers to their Discord accounts.

It does **not** read messages, send DMs, moderate conversations, or need **Administrator** permission. Its only requested server permission is **Manage Roles**. Announcements use a separate webhook: a special posting link for one channel. The bot does not need **Manage Webhooks**.

The setup has been tested end to end on a private test server. We still need to check it in Metagame's server after setup.

## Who needs permission?

One server owner or suitably authorized admin can do everything. Otherwise, these tasks can be shared:

| Task | Permission needed by the person doing it |
| --- | --- |
| Invite the bot | **Manage Server**, or be the server owner |
| Create the volunteer role and arrange roles | **Manage Roles**, with your own highest role above the roles you are arranging, or be the server owner |
| Create the announcement webhook | **Manage Webhooks** in the chosen channel |
| Enable Developer Mode and copy IDs | No extra permission to enable Developer Mode; access to **Server Settings → Roles** is needed for the role-copy step below |

Do not give volunteers administrative permissions. The volunteer role can simply be a label; give it channel access only if your team wants that.

## Setup: follow these steps in order

### 1. Invite the bot

Open this invitation while signed in to the Discord account that manages Metagame:

<https://discord.com/oauth2/authorize?client_id=YOUR_APPLICATION_ID&scope=bot&permissions=268435456>

Select the Metagame server and approve the invitation. The app should be **Metagame Shift Bot**, requesting **Manage Roles** only. If the server is not available to select, ask the server owner or someone with **Manage Server** to do this step.

The application ID in this link identifies the bot, not your server.

### 2. Create the volunteer role

1. Open the menu next to the server name.
2. Choose **Server Settings → Roles → Create Role**.
3. Name the role exactly **On-shift Volunteer**.
4. Choose a color if you like. Leave administrative permissions off. Save your changes.

Use a dedicated role, not an existing general volunteer or staff role. **The bot removes this role from anyone who is not scheduled, even if an admin gave it to them.**

### 3. Put the roles in the right order

1. Stay in **Server Settings → Roles**.
2. Find the bot's own role, normally **Metagame Shift Bot**.
3. Drag that role **above On-shift Volunteer**. Save any pending changes.

The bot can manage only roles below its highest role. It does not need to be above your admin or moderator roles.

### 4. Create the channel's webhook

1. Choose the text channel where on-shift announcements should appear. Make sure volunteers can see it.
2. Open **Server Settings → Integrations → Webhooks**.
3. Choose **Create Webhook**. If a webhook already exists, Discord may instead show **New Webhook** to add another. Create a separate one for this bot.
4. Name it **Metagame Shifts** and select the on-shift volunteer channel in its channel selector. Save your changes.
5. Select **Copy Webhook URL**.
6. **Send that URL to YOUR_BOT_CONTACT by Discord DM, never in a server channel.** Anyone with it can post through the webhook. Do not put it in screenshots, public documents, or code.

The channel is selected in the webhook settings; you do not need to send a Channel ID. If the URL leaks, delete that webhook, create a replacement, and send the new URL privately.

### 5. Turn on Developer Mode and copy two IDs

Developer Mode only shows extra copy options. It does not give the bot extra access.

1. Open the cogwheel by your account to reach **User Settings → Advanced → Developer Mode**. Turn it on.
2. Return to the server. Right-click its icon and choose **Copy Server ID**. Paste it into a draft message labeled `Server ID`.
3. Open **Server Settings → Roles**. Right-click **On-shift Volunteer** and choose **Copy Role ID**. Paste it labeled `Role ID`.

Copy the volunteer role's ID, not the bot role's ID. These are long numbers; copy and paste rather than typing them. They are not the application ID in the invitation.

### 6. Send the setup details back

Send YOUR_BOT_CONTACT a Discord DM containing:

- **Server ID:** the copied server number.
- **Role ID:** the copied **On-shift Volunteer** role number.
- **Webhook URL:** the secret URL copied in step 4.
- A short confirmation that the bot role is above **On-shift Volunteer**, and the name of the announcement channel.

**Keep the webhook URL private even if you share the IDs elsewhere.** Do not send a bot token, your password, or a login code. Ask YOUR_BOT_CONTACT to confirm setup and arrange a watched check of role assignment, removal, and the announcement before relying on it.

## What volunteers will see

**Event timing:** YOUR_EVENT_SCHEDULE Allow roughly a minute for a schedule change to appear.

- A volunteer starting a shift gets **On-shift Volunteer** and a mention in the announcement channel. Whether Discord sends a notification depends on their notification settings.
- Someone continuing straight into another shift keeps the role without another announcement.
- At the end of a shift, the role is removed unless another shift continues. The bot does not post a separate end-of-shift message or send a DM.
- Volunteers must be in the server and have the correct Discord handle in the mapping list. A renamed or missing handle can mean no role; tell YOUR_BOT_CONTACT so the mapping can be corrected.

**Do not hand this role out manually.** Unscheduled holders lose it on the next successful check. Removing it manually from someone who is still on shift causes the bot to add it back on the next check, normally within a minute, and announce them again. Make schedule corrections through YOUR_BOT_CONTACT instead.

## Troubleshooting

| What you notice | What to check |
| --- | --- |
| No one gets the role | In **Server Settings → Roles**, put the bot's role above **On-shift Volunteer**. Check that the bot still has **Manage Roles**. Confirm that the IDs sent back were for this server and the volunteer role. |
| A setup button or menu is missing | Ask the server owner to check your **Manage Server**, **Manage Roles**, or **Manage Webhooks** permission for the task. Do not solve this by giving the bot **Administrator**. |
| One person does not get the role | Confirm their shift time is Pacific time, they joined this server, and their current Discord handle matches the mapping. Send YOUR_BOT_CONTACT their current handle and expected shift privately; do not guess or change IDs. An unresolved active volunteer can also hold up role updates for everyone until the mismatch is fixed. |
| Roles change but no announcement appears | Check the webhook's selected channel and volunteers' channel access. Tell YOUR_BOT_CONTACT if the webhook was deleted or replaced. Send any replacement URL privately. |
| The bot looks offline | This bot works by checking once a minute rather than staying connected to Discord chat. Its presence indicator is not a reliable health check; report missed role changes to YOUR_BOT_CONTACT. |
| Updates stop or appear out of date | Contact YOUR_BOT_CONTACT with the time, expected change, and what actually happened. A schedule-fetch problem may leave the last known schedule in use. Never include the webhook URL in a public report. |

## Pause or remove it

- **Normal pause:** ask YOUR_BOT_CONTACT to stop the scheduled checks. Agree whether current roles should be cleared first. Pausing does not automatically remove roles already assigned.
- **Immediate stop:** a server owner or someone with **Kick Members** can kick **Metagame Shift Bot** from the server. Tell YOUR_BOT_CONTACT as well. Kicking stops its role changes, but the separate webhook can still post until checks are stopped or that webhook is deleted.
- **Stop announcements immediately:** delete this bot's webhook under **Server Settings → Integrations → Webhooks**. This alone does not stop role updates.
- **Full removal:** stop the checks or kick the bot, delete its webhook, and remove remaining **On-shift Volunteer** assignments if desired. Do not remove live role assignments before stopping checks, or they may be added back.
- **After the event:** allow the final check to remove the last on-shift roles before checks are switched off.

## Official Discord help

Menu wording checked against Discord's official help. These public reference links are not server invitations or private configuration:

- [Setting Up Permissions FAQ: Server Settings → Roles → Create Role](https://support.discord.com/hc/en-us/articles/206029707-Setting-Up-Permissions-FAQ)
- [Intro to Webhooks: Integrations, Create Webhook, Copy Webhook URL](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks)
- [Where can I find my User/Server/Message ID?: Developer Mode and Copy Server ID](https://support.discord.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID)
