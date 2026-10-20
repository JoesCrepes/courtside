package com.joescrepes.courtside.ui.lineup

import com.joescrepes.courtside.data.LineupIntent
import com.joescrepes.courtside.data.Player

/** ESPN's lineup order. Slots a league doesn't use have a count of 0 and are skipped. */
val SLOT_ORDER = listOf("PG", "SG", "SF", "PF", "C", "G", "F", "SG/SF", "G/F", "PF/C", "F/C", "UTIL", "BE", "IR")

const val BENCH = "BE"
const val IR = "IR"

/** One place in the lineup: a slot, and whoever is in it (null when empty). */
data class Seat(val slot: String, val player: Player?)

/** Every seat in lineup order, including empty ones. */
fun seats(roster: List<Player>, slotCounts: Map<String, Int>): List<Seat> {
    val bySlot = roster.groupBy { it.slot }
    return SLOT_ORDER.flatMap { slot ->
        val players = bySlot[slot].orEmpty()
        val count = maxOf(slotCounts[slot] ?: 0, players.size)
        List(count) { i -> Seat(slot, players.getOrNull(i)) }
    }
}

/**
 * What tapping [target] does while [selected] is picked up, or null if it's not a legal move.
 *
 * - Empty seat: move there.
 * - Starter tapped onto a bench player: that bench player comes in for the starter.
 * - Any other occupied seat: move there, swapping with that occupant when the slot is full.
 */
fun intentFor(selected: Player, target: Seat, roster: List<Player>, slotCounts: Map<String, Int>): LineupIntent? {
    val from = selected.slot ?: return null
    val occupant = target.player
    if (selected.lineupLocked || occupant?.id == selected.id) return null
    if (occupant?.lineupLocked == true) return null
    fun full(slot: String) = roster.count { it.slot == slot } >= (slotCounts[slot] ?: 0)

    if (occupant != null && target.slot == BENCH && from != BENCH) {
        if (from !in occupant.eligibleSlots) return null
        return LineupIntent(
            player = occupant.id.toString(),
            slot = from,
            swapWith = selected.id.toString().takeIf { full(from) },
        )
    }
    if (target.slot == from) return null
    if (target.slot !in selected.eligibleSlots) return null
    if (target.slot == IR && selected.injuryStatus != "OUT") return null
    return LineupIntent(
        player = selected.id.toString(),
        slot = target.slot,
        swapWith = occupant?.takeIf { target.slot != BENCH && full(target.slot) }?.id?.toString(),
    )
}
