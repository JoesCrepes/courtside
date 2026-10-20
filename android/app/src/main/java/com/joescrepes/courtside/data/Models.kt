package com.joescrepes.courtside.data

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

// Mirrors of the courtside server's JSON (server/app.py). Field names are
// converted from snake_case by Api.json.

@Serializable
data class LeagueContext(
    val scoringPeriod: Int,
    val matchupPeriod: Int,
    val teamId: Int? = null,
    val writesEnabled: Boolean = false,
    val email: String? = null,
)

@Serializable
data class StatLine(val total: Double = 0.0, val avg: Double = 0.0, val gp: Double = 0.0)

@Serializable
data class Game(val id: Long, val start: Long, val home: Boolean, val opponent: String)

@Serializable
data class Player(
    val id: Int,
    val name: String,
    val proTeam: String? = null,
    val positions: List<String> = emptyList(),
    val eligibleSlots: List<String> = emptyList(),
    val slot: String? = null,
    val isStarting: Boolean = false,
    val injuryStatus: String = "ACTIVE",
    // "FREEAGENT", "WAIVERS" or "ONTEAM".
    val status: String? = null,
    val onTeamId: Int? = null,
    val percentOwned: Double? = null,
    val lineupLocked: Boolean = false,
    val stats: Map<String, StatLine> = emptyMap(),
    val game: Game? = null,
) {
    val projected: Double? get() = stats["projected"]?.avg
    val seasonAvg: Double? get() = stats["season"]?.avg?.takeIf { (stats["season"]?.gp ?: 0.0) > 0 }
    val lastSeasonAvg: Double? get() = stats["prev_season"]?.avg
}

@Serializable
data class TeamSummary(
    val id: Int,
    val name: String,
    val abbrev: String = "",
    val logo: String? = null,
    val wins: Int = 0,
    val losses: Int = 0,
    val ties: Int = 0,
    val pointsFor: Double = 0.0,
    val pointsAgainst: Double = 0.0,
    val playoffSeed: Int? = null,
    val waiverRank: Int? = null,
)

@Serializable
data class Roster(
    val id: Int,
    val name: String,
    val abbrev: String = "",
    val logo: String? = null,
    val wins: Int = 0,
    val losses: Int = 0,
    val ties: Int = 0,
    val day: Int,
    val roster: List<Player> = emptyList(),
)

@Serializable
data class Acquisitions(
    val type: String? = null,
    val perWeek: Double? = null,
    val budget: Int? = null,
    val waiverHours: Int? = null,
)

@Serializable
data class League(
    val name: String? = null,
    val scoringType: String? = null,
    val slots: Map<String, Int> = emptyMap(),
    val acquisitions: Acquisitions = Acquisitions(),
    val standings: List<TeamSummary> = emptyList(),
)

@Serializable
data class Side(val teamId: Int, val name: String? = null, val points: Double = 0.0)

@Serializable
data class Matchup(
    val id: Int,
    val week: Int,
    val playoff: Boolean = false,
    // "HOME", "AWAY", "TIE" or "UNDECIDED".
    val winner: String = "UNDECIDED",
    val home: Side? = null,
    val away: Side? = null,
) {
    fun involves(teamId: Int?) = teamId != null && (home?.teamId == teamId || away?.teamId == teamId)
}

@Serializable
data class Scoreboard(val week: Int, val matchups: List<Matchup> = emptyList())

@Serializable
data class PlayerList(val day: Int, val players: List<Player> = emptyList())

@Serializable
data class ActivityItem(
    // "ADD", "DROP", "MOVE" or "TRADE".
    val kind: String,
    val playerId: Int,
    val player: String? = null,
    val teamId: Int? = null,
    val fromSlot: String? = null,
    val toSlot: String? = null,
)

@Serializable
data class ActivityEntry(val date: Long, val items: List<ActivityItem> = emptyList())

@Serializable
data class ActivityFeed(val activity: List<ActivityEntry> = emptyList())

@Serializable
data class LineupIntent(
    val player: String,
    val slot: String,
    val swapWith: String? = null,
    val day: Int? = null,
)

@Serializable
data class RosterIntent(
    val add: Int? = null,
    val drop: String? = null,
    val waiver: Boolean = false,
    val bid: Int? = null,
)

/** What a write would do. `expect` goes back to the server unchanged on confirm. */
@Serializable
data class Preview(
    val type: String,
    val summary: List<String>,
    val scoringPeriod: Int,
    val expect: List<JsonObject>,
)

@Serializable
data class Confirmed(
    val status: String? = null,
    val id: String? = null,
    val type: String = "",
    val summary: List<String> = emptyList(),
)
