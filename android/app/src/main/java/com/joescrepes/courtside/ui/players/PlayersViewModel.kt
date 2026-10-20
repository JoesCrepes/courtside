package com.joescrepes.courtside.ui.players

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.joescrepes.courtside.data.Api
import com.joescrepes.courtside.data.PlanChanged
import com.joescrepes.courtside.data.Player
import com.joescrepes.courtside.data.Preview
import com.joescrepes.courtside.data.RosterIntent
import com.joescrepes.courtside.ui.attempt
import com.joescrepes.courtside.ui.friendly
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class Filters(val query: String = "", val position: String? = null, val availableOnly: Boolean = true)

data class AddSheet(
    val player: Player,
    val drop: Player? = null,
    // Null until "Review" is tapped.
    val preview: Preview? = null,
    val busy: Boolean = false,
    val error: String? = null,
    val note: String? = null,
) {
    val waiver: Boolean get() = player.status == "WAIVERS"
    val intent: RosterIntent get() = RosterIntent(add = player.id, drop = drop?.id?.toString(), waiver = waiver)
}

data class PlayersUi(
    val filters: Filters = Filters(),
    val players: List<Player> = emptyList(),
    val myRoster: List<Player> = emptyList(),
    val myTeamId: Int? = null,
    val loading: Boolean = true,
    val error: String? = null,
    val sheet: AddSheet? = null,
    val message: String? = null,
)

@OptIn(FlowPreview::class)
class PlayersViewModel(private val api: Api) : ViewModel() {
    private val _ui = MutableStateFlow(PlayersUi())
    val ui: StateFlow<PlayersUi> = _ui

    init {
        viewModelScope.launch {
            // Typing debounces; chip taps go through almost immediately.
            _ui.map { it.filters }.distinctUntilChanged().debounce(250).collectLatest { search(it) }
        }
        loadMyRoster()
    }

    private suspend fun search(f: Filters) {
        _ui.update { it.copy(loading = true, error = null) }
        attempt { api.players(f.query, f.position, f.availableOnly) }
            .onSuccess { r -> _ui.update { it.copy(players = r.players, loading = false) } }
            .onFailure { e -> _ui.update { it.copy(error = e.friendly(), loading = false) } }
    }

    private fun loadMyRoster() = viewModelScope.launch {
        attempt { api.roster() }.onSuccess { r -> _ui.update { it.copy(myRoster = r.roster, myTeamId = r.id) } }
    }

    fun setQuery(q: String) = _ui.update { it.copy(filters = it.filters.copy(query = q)) }
    fun setPosition(p: String?) = _ui.update { it.copy(filters = it.filters.copy(position = p)) }
    fun setAvailableOnly(v: Boolean) = _ui.update { it.copy(filters = it.filters.copy(availableOnly = v)) }
    fun retry() = viewModelScope.launch { search(_ui.value.filters) }

    fun open(player: Player) = _ui.update { it.copy(sheet = AddSheet(player)) }
    fun dismiss() = _ui.update { it.copy(sheet = null) }

    fun chooseDrop(p: Player?) = _ui.update { it.copy(sheet = it.sheet?.copy(drop = p, preview = null, error = null, note = null)) }

    fun review() {
        val sheet = _ui.value.sheet ?: return
        _ui.update { it.copy(sheet = sheet.copy(busy = true, error = null)) }
        viewModelScope.launch {
            attempt { api.previewRoster(sheet.intent) }
                .onSuccess { p -> _ui.update { it.copy(sheet = it.sheet?.copy(preview = p, busy = false)) } }
                .onFailure { e -> _ui.update { it.copy(sheet = it.sheet?.copy(busy = false, error = e.friendly())) } }
        }
    }

    fun confirm() {
        val sheet = _ui.value.sheet ?: return
        val preview = sheet.preview ?: return
        _ui.update { it.copy(sheet = sheet.copy(busy = true, error = null)) }
        viewModelScope.launch {
            attempt { api.confirmRoster(sheet.intent, preview) }
                .onSuccess {
                    val verb = if (sheet.waiver) "Claim submitted for" else "Added"
                    _ui.update { it.copy(sheet = null, message = "$verb ${sheet.player.name}") }
                    loadMyRoster()
                    search(_ui.value.filters)
                }
                .onFailure { e ->
                    _ui.update {
                        it.copy(
                            sheet = when (e) {
                                is PlanChanged -> sheet.copy(preview = e.preview, busy = false, note = "Something changed. Here's the updated transaction.")
                                else -> sheet.copy(busy = false, error = e.friendly())
                            }
                        )
                    }
                }
        }
    }

    fun messageShown() = _ui.update { it.copy(message = null) }
}
