package com.stash.app.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface LibraryItemDao {
    @Query("SELECT * FROM library_items WHERE deletedAt IS NULL ORDER BY savedAt DESC")
    fun observeAll(): Flow<List<LibraryItemEntity>>

    @Query("SELECT * FROM library_items WHERE deletedAt IS NOT NULL ORDER BY deletedAt DESC")
    fun observeBin(): Flow<List<LibraryItemEntity>>

    @Query("SELECT * FROM library_items WHERE deletedAt IS NOT NULL ORDER BY deletedAt DESC")
    suspend fun getBinItems(): List<LibraryItemEntity>

    @Query("SELECT * FROM library_items ORDER BY savedAt DESC")
    suspend fun getAllForBackup(): List<LibraryItemEntity>

    @Query("SELECT * FROM library_folders ORDER BY name COLLATE NOCASE")
    fun observeFolders(): Flow<List<LibraryFolderEntity>>

    @Query("SELECT * FROM library_folders ORDER BY name COLLATE NOCASE")
    suspend fun getFolders(): List<LibraryFolderEntity>

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun createFolder(folder: LibraryFolderEntity): Long

    @Query("DELETE FROM library_folders WHERE name = :name")
    suspend fun deleteFolder(name: String)

    @Query("DELETE FROM library_folders WHERE name = :name AND NOT EXISTS (SELECT 1 FROM library_items WHERE folderName = :name)")
    suspend fun deleteFolderIfEmpty(name: String): Int

    @Query("SELECT * FROM library_items WHERE id = :id LIMIT 1")
    suspend fun getItem(id: String): LibraryItemEntity?

    @Query("UPDATE library_items SET folderName = :folderName WHERE id IN (:ids) AND deletedAt IS NULL")
    suspend fun moveToFolder(ids: List<String>, folderName: String?): Int

    @Query("UPDATE library_items SET tagsJson = :tagsJson WHERE id = :id AND deletedAt IS NULL")
    suspend fun updateTags(id: String, tagsJson: String)

    @Query("UPDATE library_items SET isFavorite = :isFavorite WHERE id = :id AND deletedAt IS NULL")
    suspend fun setFavorite(id: String, isFavorite: Boolean)

    @Query("UPDATE library_items SET folderName = :folderName, tagsJson = :tagsJson, isFavorite = :isFavorite WHERE id = :id")
    suspend fun restoreOrganization(id: String, folderName: String?, tagsJson: String, isFavorite: Boolean)

    @Query("UPDATE library_items SET sharedItemId = :sharedItemId WHERE id = :id")
    suspend fun setSharedItemId(id: String, sharedItemId: Long?)

    @Query("UPDATE library_items SET folderName = :folderName, tagsJson = :tagsJson, isFavorite = :isFavorite, sharedItemId = :sharedItemId WHERE id = :id")
    suspend fun updateSharedMetadata(
        id: String,
        folderName: String?,
        tagsJson: String,
        isFavorite: Boolean,
        sharedItemId: Long,
    )

    @Query("UPDATE library_items SET ocrText = :ocrText WHERE id = :id AND ocrText IS NULL")
    suspend fun updateOcrText(id: String, ocrText: String)

    @Query("SELECT COUNT(*) FROM library_items")
    suspend fun countAll(): Int

    @Insert
    suspend fun insertAll(items: List<LibraryItemEntity>)

    @Query("UPDATE library_items SET deletedAt = :deletedAt WHERE id = :id AND deletedAt IS NULL")
    suspend fun moveToBin(id: String, deletedAt: Long)

    @Query("UPDATE library_items SET deletedAt = :deletedAt WHERE id IN (:ids) AND deletedAt IS NULL")
    suspend fun moveItemsToBin(ids: List<String>, deletedAt: Long): Int

    @Query("UPDATE library_items SET deletedAt = NULL WHERE id = :id AND deletedAt IS NOT NULL")
    suspend fun restoreFromBin(id: String)

    @Query("DELETE FROM library_items WHERE id = :id AND deletedAt IS NOT NULL")
    suspend fun deleteBinnedItem(id: String)

    @Query("DELETE FROM library_items WHERE id IN (:ids)")
    suspend fun deleteByIds(ids: List<String>)
}
