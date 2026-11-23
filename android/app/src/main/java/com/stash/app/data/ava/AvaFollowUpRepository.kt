package com.stash.app.data.ava

import com.stash.app.data.local.AvaFollowUpDao
import com.stash.app.data.local.AvaFollowUpEntity
import java.util.UUID
import kotlinx.coroutines.flow.Flow

class AvaFollowUpRepository(private val dao: AvaFollowUpDao) {
    fun observeAll(): Flow<List<AvaFollowUpEntity>> = dao.observeAll()

    suspend fun allForSync(): List<AvaFollowUpEntity> = dao.getAllForSync()

    suspend fun restoreFromBackup(followUps: List<AvaFollowUpEntity>) {
        followUps.forEach { dao.upsert(it) }
    }

    suspend fun mergeRemote(followUps: List<AvaFollowUpEntity>, validSourceItemIds: Set<String>) {
        val localById = dao.getAllForSync().associateBy(AvaFollowUpEntity::id)
        followUps.filter { it.sourceItemId in validSourceItemIds }.forEach { remote ->
            val local = localById[remote.id]
            if (local == null || remote.updatedAt >= local.updatedAt) {
                dao.upsert(remote.copy(sourceExcerpt = local?.sourceExcerpt ?: remote.sourceExcerpt))
            }
        }
    }

    suspend fun getById(id: String): AvaFollowUpEntity? = dao.getById(id)

    suspend fun add(suggestion: AvaDateSuggestion, remindAt: Long): AvaFollowUpEntity? {
        val existing = dao.getForItemDate(suggestion.sourceItemId, suggestion.eventAt)
        if (existing?.deletedAt == null && existing != null) return null
        val now = System.currentTimeMillis()
        val entity = AvaFollowUpEntity(
            id = existing?.id ?: UUID.randomUUID().toString(),
            sourceItemId = suggestion.sourceItemId,
            sourceTitle = suggestion.sourceTitle,
            eventLabel = suggestion.eventLabel,
            sourceExcerpt = suggestion.sourceExcerpt,
            eventAt = suggestion.eventAt,
            remindAt = remindAt,
            createdAt = existing?.createdAt ?: now,
            updatedAt = now,
        )
        dao.upsert(entity)
        return entity
    }

    suspend fun markNotified(id: String) = dao.markNotified(id, System.currentTimeMillis())

    suspend fun delete(id: String) = dao.delete(id, System.currentTimeMillis())
}
