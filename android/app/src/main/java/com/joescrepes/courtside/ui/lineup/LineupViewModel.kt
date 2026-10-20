package com.joescrepes.courtside.ui.lineup

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.joescrepes.courtside.data.Api
import com.joescrepes.courtside.data.LineupIntent
import com.joescrepes.courtside.data.Matchup
import com.joescrepes.courtside.data.PlanChanged
import com.joescrepes.courtside.data.Player
import com.joescrepes.courtside.data.Preview
import com.joescrepes.courtside.data.Roster
import com.joescrepes.courtside.data.TeamSummary
import com.joescrepes.courtside.ui.attempt
import com.joescrepes.courtside.ui.friendly
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class MoveSheet(
    val intent: LineupIntent,
    val preview: Preview? = null,
    val busy: Boolean = true,
    val error: String? = null,
    val note: String? = null,
)

data class LineupUi(
    val today: Int? = null,
    val day: Int? = null,
    val myTeamId: Int? = null,
    val slotCounts: Map<String, Int> = emptyMap(),
    val teams: Map<Int, TeamSummary> = emptyMap(),
    val roster: Roster? = null,
    val matchup: Matchup? = null,
    val loading: Boolean = true,
    val refreshing: Boolean = false,
    val error: String? = null,
    val selected: Player? = null,
    val sheet: MoveSheet? = null,
    val message: String? = null,
) {
    val seats: List<Seat> get() = roster?.let { seats(it.roster, slotCounts) }.orEmpty()
}

class LineupViewModel(private val api: Api) : ViewModel() {
    private val _ui = MutableStateFlow(LineupUi())
    val ui: StateFlow<LineupUi> = _ui

    init {
        load()
    }

    fun load(day: Int? = _ui.value.day, pullToRefresh: Boolean = false) {
        _ui.update { it.copy(loading = !pullToRefresh && it.roster == null, refreshing = pullToRefresh, error = null, selected = null) }
        viewModelScope.launch {
            attempt {
                coroutineScope {
                    val ctx = async { api.context() }
                    val league = async { if (_ui.value.slotCounts.isEmpty()) api.league() else null }
                    val roster = async { api.roster(day) }
                    val board = async { api.scoreboard() }
                    val me = ctx.await().teamId
                    _ui.update {
                        it.copy(
                            today = ctx.await().scoringPeriod,
                            myTeamId = me,
                            slotCounts = league.await()?.slots ?: it.slotCounts,
                            teams = league.await()?.standings?.associateBy { t -> t.id } ?: it.teams,
                            roster = roster.await(),
                            day = roster.await().day,
                            matchup = board.await().matchups.firstOrNull { m -> m.involves(me) },
                        )
                    }
                }
            }.onFailure { e -> _ui.update { it.copy(error = e.friendly()) } }
            _ui.update { it.copy(loading = false, refreshing = false) }
        }
    }

    fun shiftDay(by: Int) {
        val day = (_ui.value.day ?: return) + by
        if (day >= 1) load(day)
    }

    fun goToToday() = _ui.value.today?.let { load(it) }

    fun tapSeat(seat: Seat) {
        val s = _ui.value
        val selected = s.selected
        if (selected == null) {
            // Pick up a player (not an empty seat, not someone whose game has started).
            if (seat.player != null && !seat.player.lineupLocked) _ui.update { it.copy(selected = seat.player) }
            return
        }
        if (seat.player?.id == selected.id) {
            _ui.update { it.copy(selected = null) }
            return
        }
        val roster = s.roster?.roster ?: return
        val intent = intentFor(selected, seat, roster, s.slotCounts)?.copy(day = s.day) ?: return
        _ui.update { it.copy(sheet = MoveSheet(intent)) }
        viewModelScope.launch {
            attempt { api.previewLineup(intent) }
                .onSuccess { p -> _ui.update { it.copy(sheet = it.sheet?.copy(preview = p, busy = false)) } }
                .onFailure { e -> _ui.update { it.copy(sheet = it.sheet?.copy(busy = false, error = e.friendly())) } }
        }
    }

    fun cancelSelection() = _ui.update { it.copy(selected = null) }

    fun dismissSheet() = _ui.update { it.copy(sheet = null) }

    fun confirm() {
        val sheet = _ui.value.sheet ?: return
        val preview = sheet.preview ?: return
        _ui.update { it.copy(sheet = sheet.copy(busy = true, error = null)) }
        viewModelScope.launch {
            attempt { api.confirmLineup(sheet.intent, preview) }
                .onSuccess {
                    _ui.update { it.copy(sheet = null, selected = null, message = "Lineup updated") }
                    load()
                }
                .onFailure { e ->
                    _ui.update {
                        it.copy(
                            sheet = when (e) {
                                is PlanChanged -> sheet.copy(preview = e.preview, busy = false, note = "Your roster changed. Here's the updated move.")
                                else -> sheet.copy(busy = false, error = e.friendly())
                            }
                        )
                    }
                }
        }
    }

    fun messageShown() = _ui.update { it.copy(message = null) }
}
