# ============================================================
# 🚀 SNIPER v51 — DOPPIA AMBATA + EVENTI AMBO
#
# NOVITÀ:
# ✅ SUPER AMBATA PRINCIPALE
# ✅ AMBATA OMBRA (shadow)
# ✅ switch più stabile
# ✅ eventi ambo separati
# ✅ cluster persistenti
# ============================================================

SWITCH_THRESHOLD = 35

# ============================================================
# NEL __init__()
# ============================================================

self.current_super_ambata = None
self.current_super_score = 0

self.shadow_ambata = None
self.shadow_score = 0

self.total_shadow_hit = 0

# ============================================================
# SAVE STATE
# ============================================================

"current_super_ambata": self.current_super_ambata,
"current_super_score": self.current_super_score,

"shadow_ambata": self.shadow_ambata,
"shadow_score": self.shadow_score,

"total_shadow_hit": self.total_shadow_hit,

# ============================================================
# LOAD STATE
# ============================================================

self.current_super_ambata = data.get("current_super_ambata")
self.current_super_score = data.get("current_super_score", 0)

self.shadow_ambata = data.get("shadow_ambata")
self.shadow_score = data.get("shadow_score", 0)

self.total_shadow_hit = data.get("total_shadow_hit", 0)

# ============================================================
# SUPER AMBATA ENGINE
# ============================================================

scores = self.build_super_ambata(e)

if scores:

    main = scores[0]

    main_n = main["number"]
    main_score = main["score"]

    shadow = None

    if len(scores) > 1:
        shadow = scores[1]

    # ========================================================
    # FIRST INIT
    # ========================================================

    if self.current_super_ambata is None:

        self.current_super_ambata = main_n
        self.current_super_score = main_score

        if shadow:
            self.shadow_ambata = shadow["number"]
            self.shadow_score = shadow["score"]

        await self.tg(
            app,
            "🔥 DOPPIA AMBATA ATTIVA v51\n"
            f"• MAIN = {self.current_super_ambata}\n"
            f"• SHADOW = {self.shadow_ambata}\n"
            f"• score main = {self.current_super_score}\n"
            f"• score shadow = {self.shadow_score}"
        )

    # ========================================================
    # SWITCH MAIN
    # ========================================================

    else:

        if (

            main_n != self.current_super_ambata

            and

            main_score >
            self.current_super_score + SWITCH_THRESHOLD
        ):

            old_main = self.current_super_ambata

            # vecchia main diventa shadow
            self.shadow_ambata = old_main
            self.shadow_score = self.current_super_score

            # nuova main
            self.current_super_ambata = main_n
            self.current_super_score = main_score

            self.total_ambata_switch += 1

            await self.tg(
                app,
                "🔁 SWITCH MAIN v51\n"
                f"• MAIN: {old_main} → {main_n}\n"
                f"• nuova SHADOW = {self.shadow_ambata}\n"
                f"• new score = {main_score}"
            )

        else:

            self.current_super_score = main_score

            if shadow:

                if shadow["number"] != self.current_super_ambata:

                    self.shadow_ambata = shadow["number"]
                    self.shadow_score = shadow["score"]

    # ========================================================
    # HIT MAIN
    # ========================================================

    if self.current_super_ambata in s:

        self.total_ambata_hit += 1

        await self.tg(
            app,
            "🎯 HIT MAIN AMBATA v51\n"
            f"• numero = {self.current_super_ambata}\n"
            f"• score = {self.current_super_score}\n\n"
            f"📊 STATS\n"
            f"• hit main = {self.total_ambata_hit}\n"
            f"• hit shadow = {self.total_shadow_hit}\n"
            f"• switch = {self.total_ambata_switch}"
        )

    # ========================================================
    # HIT SHADOW
    # ========================================================

    if (

        self.shadow_ambata

        and

        self.shadow_ambata in s
    ):

        self.total_shadow_hit += 1

        await self.tg(
            app,
            "🌑 HIT SHADOW AMBATA v51\n"
            f"• numero = {self.shadow_ambata}\n"
            f"• score = {self.shadow_score}\n\n"
            f"📊 STATS\n"
            f"• hit main = {self.total_ambata_hit}\n"
            f"• hit shadow = {self.total_shadow_hit}\n"
            f"• switch = {self.total_ambata_switch}"
        )

# ============================================================
# REPORT
# ============================================================

await self.tg(
    app,
    "📊 REPORT v51\n\n"

    f"🔥 MAIN AMBATA\n"
    f"• numero = {self.current_super_ambata}\n"
    f"• score = {self.current_super_score}\n"
    f"• hit = {self.total_ambata_hit}\n\n"

    f"🌑 SHADOW AMBATA\n"
    f"• numero = {self.shadow_ambata}\n"
    f"• score = {self.shadow_score}\n"
    f"• hit = {self.total_shadow_hit}\n\n"

    f"🔁 SWITCH = {self.total_ambata_switch}\n\n"

    f"🔥 EVENTI AMBO\n"
    f"• play = {self.total_event_play}\n"
    f"• hit = {self.total_event_hit}\n"
    f"• stop = {self.total_event_stop}"
)
