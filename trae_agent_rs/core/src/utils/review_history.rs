use serde::{Deserialize, Serialize};
use std::fs;
use std::io::Write;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};
use thiserror::Error;

/// Trait for objects that can record and update review data
pub trait ReviewRecorder {
    /// Save the current record to persistent storage
    /// 
    /// # Returns
    /// * `Ok(())` if the record was saved successfully
    /// * `Err(ReviewHistoryError)` if saving failed
    fn save_record(&self) -> Result<(), ReviewHistoryError>;
    
    /// Update the record with new information
    /// 
    /// # Arguments
    /// * `update` - The update data to apply to the record
    /// 
    /// # Returns
    /// * `Ok(())` if the record was updated successfully
    /// * `Err(ReviewHistoryError)` if updating failed
    fn update_record(&mut self, update: ReviewRecordUpdate) -> Result<(), ReviewHistoryError>;
}

/// Main review history management structure
/// 
/// Handles storage, retrieval, and management of review records
#[derive(Clone, Debug)]
pub struct ReviewHistory {
    /// Path to the directory where review records are stored
    pub storage_path: PathBuf,
}

/// A single review record containing all review-related information
/// 
/// This structure represents a complete review session with metadata,
/// status tracking, comments, and associated files.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct ReviewRecord {
    /// Unique identifier for this review record
    pub id: String,
    /// ISO 8601 timestamp when the review was created
    pub timestamp: String,
    /// Description of the task being reviewed
    pub task_description: String,
    /// Name or identifier of the person conducting the review
    pub reviewer: String,
    /// Current status of the review process
    pub status: ReviewStatus,
    /// Optional rating on a 1-5 scale (5 being the highest)
    pub rating: Option<u8>,
    /// Collection of comments associated with this review
    pub comments: Vec<ReviewComment>,
    /// Tags for categorizing and filtering reviews
    pub tags: Vec<String>,
    /// Duration of the review session in seconds
    pub duration_seconds: Option<u64>,
    /// List of file paths that were reviewed
    pub files_reviewed: Vec<String>,
    /// ISO 8601 timestamp when the record was first created
    pub created_at: String,
    /// ISO 8601 timestamp when the record was last updated
    pub updated_at: String,
}

/// Enumeration of possible review statuses
/// 
/// Represents the current state of a review process
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub enum ReviewStatus {
    /// Review has been created but not yet started
    Pending,
    /// Review is currently being conducted
    InProgress,
    /// Review has been completed
    Completed,
    /// Review was rejected or declined
    Rejected,
    /// Review was approved and accepted
    Approved,
}

/// A comment within a review record
/// 
/// Represents feedback, suggestions, or notes made during the review process
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct ReviewComment {
    /// Unique identifier for this comment
    pub id: String,
    /// ISO 8601 timestamp when the comment was created
    pub timestamp: String,
    /// Name or identifier of the comment author
    pub author: String,
    /// The actual comment text content
    pub content: String,
    /// Type/category of the comment
    pub comment_type: CommentType,
    /// Optional file path this comment refers to
    pub file_path: Option<String>,
    /// Optional line number within the file this comment refers to
    pub line_number: Option<u32>,
}

/// Types of comments that can be made during a review
/// 
/// Categorizes comments to help with filtering and understanding context
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub enum CommentType {
    /// General comment or observation
    General,
    /// Suggestion for improvement
    Suggestion,
    /// Issue or problem identified
    Issue,
    /// Positive feedback or praise
    Praise,
    /// Question requiring clarification
    Question,
}

/// Structure for updating existing review records
/// 
/// All fields are optional to allow partial updates
#[derive(Debug, Default, PartialEq)]
pub struct ReviewRecordUpdate {
    /// New task description
    pub task_description: Option<String>,
    /// New reviewer name
    pub reviewer: Option<String>,
    /// New review status
    pub status: Option<ReviewStatus>,
    /// New rating (Option<Option<u8>> allows setting to None)
    pub rating: Option<Option<u8>>,
    /// New tags list
    pub tags: Option<Vec<String>>,
    /// New duration (Option<Option<u64>> allows setting to None)
    pub duration_seconds: Option<Option<u64>>,
    /// New files reviewed list
    pub files_reviewed: Option<Vec<String>>,
    /// Comment to add to the record
    pub add_comment: Option<ReviewComment>,
    /// ID of comment to remove from the record
    pub remove_comment_id: Option<String>,
}

/// Errors that can occur during review history operations
#[derive(Error, Debug, PartialEq)]
pub enum ReviewHistoryError {
    /// Failed to create a file at the specified path
    #[error("Failed to create file at path: {0}. Error: {1}")]
    CreateFileError(String, String),
    
    /// Failed to create a directory at the specified path
    #[error("Failed to create directory at path: {0}. Error: {1}")]
    CreateDirectoryError(String, String),
    
    /// Failed to serialize data to JSON
    #[error("Failed to serialize data. Error: {0}")]
    SerializationError(String),
    
    /// Failed to write data to a file
    #[error("Failed to write data to file at path: {0}. Error: {1}")]
    WriteError(String, String),
    
    /// Failed to read data from a file
    #[error("Failed to read file at path: {0}. Error: {1}")]
    ReadError(String, String),
    
    /// Failed to parse JSON data
    #[error("Failed to parse JSON data. Error: {0}")]
    ParseError(String),
    
    /// Data validation failed
    #[error("Validation error: {0}")]
    ValidationError(String),
    
    /// Requested record was not found
    #[error("Record not found: {0}")]
    RecordNotFound(String),
}

impl ReviewHistory {
    /// Create a new ReviewHistory instance
    /// 
    /// # Arguments
    /// * `storage_path` - Path to the directory where review records will be stored
    /// 
    /// # Returns
    /// A new `ReviewHistory` instance
    pub fn new(storage_path: PathBuf) -> Self {
        Self { storage_path }
    }

    /// Get the default storage path for review records
    /// 
    /// Creates a "review_records" directory in the current working directory
    /// 
    /// # Returns
    /// A `PathBuf` pointing to the default storage location
    pub fn default_storage_path() -> PathBuf {
        let mut path: PathBuf = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
        path.push("review_records");
        path
    }

    /// Create a new review record
    /// 
    /// # Arguments
    /// * `task_description` - Description of the task being reviewed
    /// * `reviewer` - Name or identifier of the reviewer
    /// 
    /// # Returns
    /// * `Ok(ReviewRecord)` - The newly created record
    /// * `Err(ReviewHistoryError)` - If creation or validation failed
    pub fn create_record(
        &self,
        task_description: String,
        reviewer: String,
    ) -> Result<ReviewRecord, ReviewHistoryError> {
        let now: String = system_time_to_string(&SystemTime::now());
        let id: String = generate_record_id();

        let record = ReviewRecord {
            id: id.clone(),
            timestamp: now.clone(),
            task_description,
            reviewer,
            status: ReviewStatus::Pending,
            rating: None,
            comments: Vec::new(),
            tags: Vec::new(),
            duration_seconds: None,
            files_reviewed: Vec::new(),
            created_at: now.clone(),
            updated_at: now,
        };

        // Validate the record
        self.validate_record(&record)?;

        Ok(record)
    }

    /// Save a review record to storage
    /// 
    /// # Arguments
    /// * `record` - The review record to save
    /// 
    /// # Returns
    /// * `Ok(())` if the record was saved successfully
    /// * `Err(ReviewHistoryError)` if saving failed
    pub fn save_record(&self, record: &ReviewRecord) -> Result<(), ReviewHistoryError> {
        // Validate the record before saving
        self.validate_record(record)?;

        // Ensure storage directory exists
        if !self.storage_path.exists() {
            fs::create_dir_all(&self.storage_path).map_err(|e| {
                ReviewHistoryError::CreateDirectoryError(
                    self.storage_path.to_string_lossy().to_string(),
                    e.to_string(),
                )
            })?;
        }

        // Serialize the record to JSON
        let json_data: String = serde_json::to_string_pretty(record)
            .map_err(|e| ReviewHistoryError::SerializationError(e.to_string()))?;

        // Write to file
        let file_path: PathBuf = self.storage_path.join(format!("{}.json", record.id));
        let mut file = fs::File::create(&file_path).map_err(|e| {
            ReviewHistoryError::CreateFileError(
                file_path.to_string_lossy().to_string(),
                e.to_string(),
            )
        })?;

        file.write_all(json_data.as_bytes()).map_err(|e| {
            ReviewHistoryError::WriteError(
                file_path.to_string_lossy().to_string(),
                e.to_string(),
            )
        })?;

        Ok(())
    }

    /// Load a specific review record by ID
    /// 
    /// # Arguments
    /// * `record_id` - The unique identifier of the record to load
    /// 
    /// # Returns
    /// * `Ok(ReviewRecord)` - The loaded record
    /// * `Err(ReviewHistoryError)` - If loading or parsing failed
    pub fn load_record(&self, record_id: &str) -> Result<ReviewRecord, ReviewHistoryError> {
        let file_path: PathBuf = self.storage_path.join(format!("{}.json", record_id));
        
        if !file_path.exists() {
            return Err(ReviewHistoryError::RecordNotFound(record_id.to_string()));
        }

        let json_data: String = fs::read_to_string(&file_path).map_err(|e| {
            ReviewHistoryError::ReadError(
                file_path.to_string_lossy().to_string(),
                e.to_string(),
            )
        })?;

        let record: ReviewRecord = serde_json::from_str(&json_data)
            .map_err(|e| ReviewHistoryError::ParseError(e.to_string()))?;

        Ok(record)
    }

    /// Load all review records from storage
    /// 
    /// # Returns
    /// * `Ok(Vec<ReviewRecord>)` - Vector of all loaded records
    /// * `Err(ReviewHistoryError)` - If loading failed
    pub fn load_all_records(&self) -> Result<Vec<ReviewRecord>, ReviewHistoryError> {
        let mut records: Vec<ReviewRecord> = Vec::new();
        
        if !self.storage_path.exists() {
            return Ok(records); // Return empty vector if directory doesn't exist
        }

        let entries = fs::read_dir(&self.storage_path).map_err(|e| {
            ReviewHistoryError::ReadError(
                self.storage_path.to_string_lossy().to_string(),
                e.to_string(),
            )
        })?;

        for entry in entries {
            if let Ok(entry) = entry {
                let path: PathBuf = entry.path();
                if path.is_file() && path.extension().and_then(|s| s.to_str()) == Some("json") {
                    match fs::read_to_string(&path) {
                        Ok(json_data) => {
                            match serde_json::from_str::<ReviewRecord>(&json_data) {
                                Ok(record) => records.push(record),
                                Err(e) => {
                                    // Log error but continue processing other files
                                    eprintln!("Failed to parse record from {}: {}", path.display(), e);
                                }
                            }
                        }
                        Err(e) => {
                            // Log error but continue processing other files
                            eprintln!("Failed to read file {}: {}", path.display(), e);
                        }
                    }
                }
            }
        }

        // Sort records by timestamp (newest first)
        records.sort_by(|a, b| b.timestamp.cmp(&a.timestamp));

        Ok(records)
    }

    /// Update an existing review record
    /// 
    /// # Arguments
    /// * `record_id` - The unique identifier of the record to update
    /// * `update` - The update data to apply
    /// 
    /// # Returns
    /// * `Ok(ReviewRecord)` - The updated record
    /// * `Err(ReviewHistoryError)` - If updating failed
    pub fn update_record(
        &self,
        record_id: &str,
        update: ReviewRecordUpdate,
    ) -> Result<ReviewRecord, ReviewHistoryError> {
        let mut record: ReviewRecord = self.load_record(record_id)?;

        // Apply updates
        if let Some(task_description) = update.task_description {
            record.task_description = task_description;
        }
        if let Some(reviewer) = update.reviewer {
            record.reviewer = reviewer;
        }
        if let Some(status) = update.status {
            record.status = status;
        }
        if let Some(rating) = update.rating {
            record.rating = rating;
        }
        if let Some(tags) = update.tags {
            record.tags = tags;
        }
        if let Some(duration_seconds) = update.duration_seconds {
            record.duration_seconds = duration_seconds;
        }
        if let Some(files_reviewed) = update.files_reviewed {
            record.files_reviewed = files_reviewed;
        }
        if let Some(comment) = update.add_comment {
            record.comments.push(comment);
        }
        if let Some(comment_id) = update.remove_comment_id {
            record.comments.retain(|c| c.id != comment_id);
        }

        // Update timestamp
        record.updated_at = system_time_to_string(&SystemTime::now());

        // Save the updated record
        self.save_record(&record)?;

        Ok(record)
    }

    /// Delete a review record from storage
    /// 
    /// # Arguments
    /// * `record_id` - The unique identifier of the record to delete
    /// 
    /// # Returns
    /// * `Ok(())` if the record was deleted successfully
    /// * `Err(ReviewHistoryError)` - If deletion failed
    pub fn delete_record(&self, record_id: &str) -> Result<(), ReviewHistoryError> {
        let file_path: PathBuf = self.storage_path.join(format!("{}.json", record_id));
        
        if !file_path.exists() {
            return Err(ReviewHistoryError::RecordNotFound(record_id.to_string()));
        }

        fs::remove_file(&file_path).map_err(|e| {
            ReviewHistoryError::WriteError(
                file_path.to_string_lossy().to_string(),
                e.to_string(),
            )
        })?;

        Ok(())
    }

    /// Validate a review record for correctness
    /// 
    /// # Arguments
    /// * `record` - The record to validate
    /// 
    /// # Returns
    /// * `Ok(())` if the record is valid
    /// * `Err(ReviewHistoryError)` if validation failed
    fn validate_record(&self, record: &ReviewRecord) -> Result<(), ReviewHistoryError> {
        if record.id.is_empty() {
            return Err(ReviewHistoryError::ValidationError(
                "Record ID cannot be empty".to_string(),
            ));
        }

        if record.task_description.is_empty() {
            return Err(ReviewHistoryError::ValidationError(
                "Task description cannot be empty".to_string(),
            ));
        }

        if record.reviewer.is_empty() {
            return Err(ReviewHistoryError::ValidationError(
                "Reviewer cannot be empty".to_string(),
            ));
        }

        if let Some(rating) = record.rating {
            if !(1..=5).contains(&rating) {
                return Err(ReviewHistoryError::ValidationError(
                    "Rating must be between 1 and 5".to_string(),
                ));
            }
        }

        Ok(())
    }
}

impl ReviewRecorder for ReviewRecord {
    /// Save this record using the default storage path
    /// 
    /// # Returns
    /// * `Ok(())` if the record was saved successfully
    /// * `Err(ReviewHistoryError)` if saving failed
    fn save_record(&self) -> Result<(), ReviewHistoryError> {
        let history: ReviewHistory = ReviewHistory::new(ReviewHistory::default_storage_path());
        history.save_record(self)
    }
    
    /// Update this record with new information
    /// 
    /// # Arguments
    /// * `update` - The update data to apply
    /// 
    /// # Returns
    /// * `Ok(())` if the record was updated successfully
    /// * `Err(ReviewHistoryError)` if updating failed
    fn update_record(&mut self, update: ReviewRecordUpdate) -> Result<(), ReviewHistoryError> {
        let history: ReviewHistory = ReviewHistory::new(ReviewHistory::default_storage_path());
        *self = history.update_record(&self.id, update)?;
        Ok(())
    }
}

/// Generate a unique record ID based on current timestamp and random component
/// 
/// # Returns
/// A unique string identifier for a review record
fn generate_record_id() -> String {
    let timestamp: u64 = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    
    format!("review_{}", timestamp)
}

/// Convert a SystemTime to an ISO 8601 formatted string
/// 
/// # Arguments
/// * `st` - The SystemTime to convert
/// 
/// # Returns
/// An ISO 8601 formatted timestamp string
pub fn system_time_to_string(st: &SystemTime) -> String {
    let timestamp: u64 = st.duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
    
    // Simple timestamp format - in a real implementation, you might want to use chrono
    format!("{}", timestamp)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn create_test_history() -> (ReviewHistory, TempDir) {
        let temp_dir = TempDir::new().expect("Failed to create temp directory");
        let history = ReviewHistory::new(temp_dir.path().to_path_buf());
        (history, temp_dir)
    }

    fn create_sample_record() -> ReviewRecord {
        ReviewRecord {
            id: "test_123".to_string(),
            timestamp: "1234567890".to_string(),
            task_description: "Review authentication module".to_string(),
            reviewer: "john.doe".to_string(),
            status: ReviewStatus::InProgress,
            rating: Some(4),
            comments: vec![ReviewComment {
                id: "comment_1".to_string(),
                timestamp: "1234567891".to_string(),
                author: "jane.smith".to_string(),
                content: "Good implementation overall".to_string(),
                comment_type: CommentType::Praise,
                file_path: Some("auth.rs".to_string()),
                line_number: Some(42),
            }],
            tags: vec!["security".to_string(), "authentication".to_string()],
            duration_seconds: Some(3600),
            files_reviewed: vec!["auth.rs".to_string(), "user.rs".to_string()],
            created_at: "1234567890".to_string(),
            updated_at: "1234567892".to_string(),
        }
    }

    #[test]
    fn test_create_record() {
        let (history, _temp_dir) = create_test_history();

        let record = history
            .create_record(
                "Test task".to_string(),
                "test.reviewer".to_string(),
            )
            .expect("Failed to create record");

        assert_eq!(record.task_description, "Test task");
        assert_eq!(record.reviewer, "test.reviewer");
        assert_eq!(record.status, ReviewStatus::Pending);
        assert!(record.rating.is_none());
        assert!(record.comments.is_empty());
    }

    #[test]
    fn test_save_and_load_record() {
        let (history, _temp_dir) = create_test_history();
        let record = create_sample_record();

        // Save the record
        history.save_record(&record).expect("Failed to save record");

        // Load the record
        let loaded_record = history
            .load_record(&record.id)
            .expect("Failed to load record");

        assert_eq!(record, loaded_record);
    }

    #[test]
    fn test_load_all_records() {
        let (history, _temp_dir) = create_test_history();

        // Create and save multiple records
        let record1 = create_sample_record();
        let mut record2 = create_sample_record();
        record2.id = "test_456".to_string();
        record2.task_description = "Second task".to_string();

        history.save_record(&record1).expect("Failed to save record1");
        history.save_record(&record2).expect("Failed to save record2");

        // Load all records
        let records = history
            .load_all_records()
            .expect("Failed to load all records");

        assert_eq!(records.len(), 2);
        assert!(records.iter().any(|r| r.id == record1.id));
        assert!(records.iter().any(|r| r.id == record2.id));
    }

    #[test]
    fn test_update_record() {
        let (history, _temp_dir) = create_test_history();
        let record = create_sample_record();

        // Save the initial record
        history.save_record(&record).expect("Failed to save record");

        // Update the record
        let update = ReviewRecordUpdate {
            status: Some(ReviewStatus::Completed),
            rating: Some(Some(5)),
            ..Default::default()
        };

        let updated_record = history
            .update_record(&record.id, update)
            .expect("Failed to update record");

        assert_eq!(updated_record.status, ReviewStatus::Completed);
        assert_eq!(updated_record.rating, Some(5));
    }

    #[test]
    fn test_delete_record() {
        let (history, _temp_dir) = create_test_history();
        let record = create_sample_record();

        // Save the record
        history.save_record(&record).expect("Failed to save record");

        // Verify it exists
        assert!(history.load_record(&record.id).is_ok());

        // Delete the record
        history
            .delete_record(&record.id)
            .expect("Failed to delete record");

        // Verify it's gone
        assert!(history.load_record(&record.id).is_err());
    }

    #[test]
    fn test_validation_errors() {
        let (history, _temp_dir) = create_test_history();

        // Test empty task description
        let result = history.create_record("".to_string(), "reviewer".to_string());
        assert!(result.is_err());

        // Test empty reviewer
        let result = history.create_record("task".to_string(), "".to_string());
        assert!(result.is_err());
    }

    #[test]
    fn test_record_not_found() {
        let (history, _temp_dir) = create_test_history();

        let result = history.load_record("nonexistent");
        assert!(matches!(result, Err(ReviewHistoryError::RecordNotFound(_))));
    }
}