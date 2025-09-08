use serde::Serialize;
use std::vec;
use std::{fs, time::SystemTime};
use thiserror::Error;

use std::io::{self, Write};
use std::path::Path;
use std::time::UNIX_EPOCH;

use crate::base_agent::AgentStep;

// every recorde should have CRU feature
pub trait Recorder {
    fn write_record(&self) -> Result<(), TrajectoryError>;
    fn update_record(&mut self, update: TrajectoryDataUpdate) -> Result<(), TrajectoryError>;
    fn save_record(&self) -> Result<(), TrajectoryError>;
}
#[derive(Clone)]
pub struct Trajectory {
    pub path: String,
    pub start_time: String,
    pub trajectory_data: Option<TrajectoryData>,
}

#[derive(Serialize, Clone, PartialEq, Debug)]
pub struct TrajectoryData {
    pub task: String,
    pub start_time: String,
    pub end_time: Option<String>,
    pub provider: String,
    pub model: String,
    pub max_step: u64,
    pub llm_interaction: Vec<LLMRecord>,
    pub success: bool,
    pub final_result: Option<String>,
    pub execution_time: f64,
}

#[derive(Debug, Default, PartialEq)]
pub struct TrajectoryDataUpdate {
    pub task: Option<String>,
    pub start_time: Option<String>,
    pub end_time: Option<String>,
    pub provider: Option<String>,
    pub model: Option<String>,
    pub max_step: Option<u64>,
    pub llm_interaction: Option<Vec<LLMRecord>>,
    pub success: Option<bool>,
    pub final_result: Option<Option<String>>, // Some(Some(v)) to set; Some(None) to clear; None to leave unchanged
    pub execution_time: Option<f64>,
}

#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct LLMRecord {
    pub content: String, // we only save text content ?
    pub token_usage: Option<u128>,
    pub model: Option<String>,
    pub provider: Option<String>,
    pub llmdetails: Option<TrajectoryDetails>,
    pub steps: Option<AgentStep>,
}

#[derive(Serialize, Clone, Debug, PartialEq)]
pub enum TrajectoryDetails {
    Chat {
        messages: Vec<String>,
        temperature: f32,
    },
    Embedding {
        dims: usize,
    },
    Completion {
        prompt_tokens: u32,
        completion_tokens: u32,
    },
}

impl Trajectory {
    pub fn start_recording(&mut self, task: &str, provider: &str, model: &str, max_step: u64) {
        if let Some(trajectory) = &mut self.trajectory_data {
            trajectory.task = task.to_string();
            trajectory.start_time = system_time_to_string(&SystemTime::now());
            trajectory.max_step = max_step;
            trajectory.provider = provider.to_string();
            trajectory.model = model.to_string();
        } else {
            self.trajectory_data = Some(TrajectoryData {
                task: task.to_string(),
                start_time: system_time_to_string(&SystemTime::now()),
                end_time: None,
                provider: provider.to_string(),
                model: model.to_string(),
                max_step,
                llm_interaction: vec![],
                success: false,
                final_result: None,
                execution_time: 0.0,
            })
        }
    }
}

impl Recorder for Trajectory {
    fn save_record(&self) -> Result<(), TrajectoryError> {
        let trajectory_path = Path::new(&self.path);
        if let Some(parent_dir) = trajectory_path.parent()
            && let Err(e) = fs::create_dir_all(parent_dir)
        {
            return Err(TrajectoryError::CreateDirectoryError(
                parent_dir.to_string_lossy().to_string(),
                e.to_string(),
            ));
        }

        let file = match fs::File::create(trajectory_path) {
            Ok(f) => f,
            Err(e) => {
                return Err(TrajectoryError::CreateFileError(
                    self.path.clone(),
                    e.to_string(),
                ));
            }
        };
        let mut writer = io::BufWriter::new(file);

        let serializable_data = self.trajectory_data.as_ref().unwrap().to_serializable();

        let json_string = match serde_json::to_string_pretty(&serializable_data) {
            Ok(json) => json,
            Err(e) => {
                return Err(TrajectoryError::SerializationError(e.to_string()));
            }
        };
        if let Err(e) = writer.write_all(json_string.as_bytes()) {
            return Err(TrajectoryError::WriteError(
                self.path.clone(),
                e.to_string(),
            ));
        }
        // If everything succeeded, return Ok.
        Ok(())
    }

    fn update_record(&mut self, update: TrajectoryDataUpdate) -> Result<(), TrajectoryError> {
        // Optional: validation helpers
        if let Some(ref task) = update.task
            && task.trim().is_empty()
        {
            return Err(TrajectoryError::Validation("task cannot be empty".into()));
        }
        if let Some(ref st) = update.start_time
            && st.trim().is_empty()
        {
            return Err(TrajectoryError::Validation(
                "start_time cannot be empty".into(),
            ));
        }
        if let Some(ref et) = update.end_time
            && et.trim().is_empty()
        {
            return Err(TrajectoryError::Validation(
                "end_time cannot be empty".into(),
            ));
        }
        if let Some(ref provider) = update.provider
            && provider.trim().is_empty()
        {
            return Err(TrajectoryError::Validation(
                "provider cannot be empty".into(),
            ));
        }

        if let Some(ref model) = update.model
            && model.trim().is_empty()
        {
            return Err(TrajectoryError::Validation("model cannot be empty".into()));
        }
        if let Some(ms) = update.max_step
            && ms == 0
        {
            // Example validation: max_step should be > 0
            return Err(TrajectoryError::Validation("max_step must be > 0".into()));
        }
        if let Some(exec) = update.execution_time
            && exec < 0.0
        {
            return Err(TrajectoryError::Validation(
                "execution_time cannot be negative".into(),
            ));
        }

        if let Some(v) = update.task {
            self.trajectory_data.as_mut().unwrap().task = v;
        }
        if let Some(v) = update.start_time {
            self.trajectory_data.as_mut().unwrap().start_time = v;
        }
        if let Some(v) = update.end_time {
            self.trajectory_data.as_mut().unwrap().end_time = Some(v);
        }
        if let Some(v) = update.provider {
            self.trajectory_data.as_mut().unwrap().provider = v;
        }
        if let Some(v) = update.model {
            self.trajectory_data.as_mut().unwrap().model = v;
        }
        if let Some(v) = update.max_step {
            self.trajectory_data.as_mut().unwrap().max_step = v;
        }
        if let Some(v) = update.llm_interaction {
            self.trajectory_data.as_mut().unwrap().llm_interaction = v;
        }
        if let Some(v) = update.success {
            self.trajectory_data.as_mut().unwrap().success = v;
        }
        if let Some(v) = update.final_result {
            self.trajectory_data.as_mut().unwrap().final_result = v;
        }
        if let Some(v) = update.execution_time {
            self.trajectory_data.as_mut().unwrap().execution_time = v;
        }

        Ok(())
    }

    fn write_record(&self) -> Result<(), TrajectoryError> {
        let trajectory_path = Path::new(&self.path);
        // Ensure parent directory exists
        if let Some(parent_dir) = trajectory_path.parent()
            && let Err(e) = fs::create_dir_all(parent_dir)
        {
            return Err(TrajectoryError::CreateDirectoryError(
                parent_dir.to_string_lossy().to_string(),
                e.to_string(),
            ));
        }

        // Create (truncate) the file
        let file = match fs::File::create(trajectory_path) {
            Ok(f) => f,
            Err(e) => {
                return Err(TrajectoryError::CreateFileError(
                    self.path.clone(),
                    e.to_string(),
                ));
            }
        };
        let mut writer = io::BufWriter::new(file);
        // Serialize to pretty JSON
        let serializable_data = self.trajectory_data.as_ref().unwrap().to_serializable();
        let json_string = match serde_json::to_string_pretty(&serializable_data) {
            Ok(json) => json,
            Err(e) => {
                return Err(TrajectoryError::SerializationError(e.to_string()));
            }
        };
        // Write all
        if let Err(e) = writer.write_all(json_string.as_bytes()) {
            return Err(TrajectoryError::WriteError(
                self.path.clone(),
                e.to_string(),
            ));
        }
        Ok(())
    }
}

#[derive(Error, Debug, PartialEq)]
pub enum TrajectoryError {
    #[error("Create File file at path:{0}. Error message: {0}")]
    CreateFileError(String, String),

    #[error("Create Directory fail at path {0}. Error message{0}")]
    CreateDirectoryError(String, String),

    #[error("Fail to serialize the data error message: {0}")]
    SerializationError(String),

    #[error("Fail to write the data to the json file to path: {0} with the error message {0}")]
    WriteError(String, String),

    #[error("Can not validate the data {0}")]
    Validation(String),
}

pub fn system_time_to_string(st: &SystemTime) -> String {
    st.duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs().to_string())
        .unwrap_or_else(|_| "N/A".to_string())
}

impl TrajectoryData {
    fn to_serializable(&self) -> TrajectoryData {
        TrajectoryData {
            task: self.task.clone(),
            start_time: self.start_time.clone(),
            end_time: self.end_time.clone(),
            provider: self.provider.clone(),
            model: self.model.clone(),
            max_step: self.max_step,
            llm_interaction: self.llm_interaction.clone(),
            success: self.success,
            final_result: self.final_result.clone(),
            execution_time: self.execution_time,
        }
    }
}

// UNIT TEST:
#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::io::Read;
    use std::path::Path;
    use tempfile::TempDir;
    use tempfile::tempdir;

    fn sample_trajectory(path: impl Into<String>) -> Trajectory {
        Trajectory {
            path: path.into(),
            start_time: "0".to_string(),
            trajectory_data: Some(TrajectoryData {
                task: "test-task".to_string(),
                start_time: "1234567890".to_string(),
                end_time: Some("1234567899".to_string()),
                provider: "openai".to_string(),
                model: "gpt-4o".to_string(),
                max_step: 5,
                llm_interaction: vec![],
                success: true,
                final_result: Some("done".to_string()),
                execution_time: 1.23,
            }),
        }
    }

    fn read_to_string<P: AsRef<Path>>(path: P) -> String {
        let mut s = String::new();
        let mut f = fs::File::open(path).expect("open file");
        f.read_to_string(&mut s).expect("read file");
        s
    }

    #[test]
    fn save_record_creates_missing_parent_dir_and_writes_json() {
        // Arrange: a fresh temp directory
        let tmp = TempDir::new().expect("tempdir");
        let nested_dir = tmp.path().join("deep/nested/dir");
        let file_path = nested_dir.join("trajectory.json");
        let t = sample_trajectory(file_path.to_string_lossy().to_string());

        // Act
        t.save_record().expect("save_record should succeed");

        // Assert: directory and file exist
        assert!(
            nested_dir.exists() && nested_dir.is_dir(),
            "parent directories should exist"
        );
        assert!(
            file_path.exists() && file_path.is_file(),
            "file should be created"
        );

        // Assert: JSON content matches serialized data
        let content = read_to_string(&file_path);

        // Parse to JSON and verify fields
        let v: serde_json::Value = serde_json::from_str(&content).expect("valid json");
        assert_eq!(v["task"], "test-task");
        assert_eq!(v["start_time"], "1234567890");
        assert_eq!(v["end_time"], "1234567899");
        assert_eq!(v["provider"], "openai");
        assert_eq!(v["model"], "gpt-4o");
        assert_eq!(v["max_step"], 5);
        assert_eq!(v["success"], true);
        assert_eq!(v["final_result"], "done");
        assert!(v["llm_interaction"].is_array());
        assert!(v["execution_time"].is_number());

        // Pretty format should contain newlines/indentation
        assert!(
            content.contains("\n"),
            "pretty JSON should contain newlines"
        );
    }

    #[test]
    fn save_record_overwrites_existing_file() {
        let tmp = TempDir::new().expect("tempdir");
        let file_path = tmp.path().join("trajectory.json");

        // Prewrite a different file
        fs::create_dir_all(file_path.parent().unwrap()).unwrap();
        fs::write(&file_path, r#"{"old":"data"}"#).unwrap();

        let t = sample_trajectory(file_path.to_string_lossy().to_string());
        t.save_record()
            .expect("save_record should succeed and overwrite");

        let content = read_to_string(&file_path);
        let v: serde_json::Value = serde_json::from_str(&content).expect("valid json");
        assert_eq!(v["task"], "test-task");
        assert!(content.contains("\n"), "still pretty printed");
        assert!(
            !content.contains(r#""old":"data""#),
            "old content should be gone"
        );
    }

    #[test]
    fn save_record_fails_when_parent_dir_is_a_file() {
        // Arrange: make a path where the "parent" is actually a file
        let tmp = TempDir::new().expect("tempdir");
        let bogus_parent = tmp.path().join("not_a_dir");
        fs::write(&bogus_parent, b"i am a file").unwrap();

        // The path attempts to create a subpath under a file, which should fail
        let file_path = bogus_parent.join("child/trajectory.json");
        let t = sample_trajectory(file_path.to_string_lossy().to_string());

        // Act
        let err = t
            .save_record()
            .expect_err("should fail creating directory under a file");

        // Assert: error kind
        match err {
            TrajectoryError::CreateDirectoryError(path, msg) => {
                assert!(
                    path.contains("not_a_dir"),
                    "path should mention failing parent"
                );
                assert!(!msg.is_empty(), "should include underlying io error");
            }
            other => panic!("unexpected error: {other:?}"),
        }
    }

    #[test]
    fn save_record_fails_when_file_creation_fails() {
        // On Unix, trying to create a file at a path that is a directory should error.
        // We create a directory at the target file path.
        let tmp = TempDir::new().expect("tempdir");
        let target = tmp.path().join("trajectory.json");
        fs::create_dir_all(&target).unwrap(); // now a dir, not a file

        let t = sample_trajectory(target.to_string_lossy().to_string());
        let err = t.save_record().expect_err("should fail on file creation");

        match err {
            TrajectoryError::CreateFileError(path, msg) => {
                assert!(
                    path.ends_with("trajectory.json"),
                    "should reference the target path"
                );
                assert!(!msg.is_empty(), "includes underlying error");
            }
            other => panic!("unexpected error: {other:?}"),
        }
    }

    #[test]
    fn save_record_fails_when_write_fails() {
        // Simulate write failure by pointing to a read-only directory
        let tmp = TempDir::new().expect("tempdir");
        let ro_dir = tmp.path().join("ro");
        fs::create_dir_all(&ro_dir).unwrap();

        // Make directory read-only (best-effort cross-platform; on Windows this is trickier)
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = fs::metadata(&ro_dir).unwrap().permissions();
            perms.set_mode(0o555); // r-x for all, no write
            fs::set_permissions(&ro_dir, perms).unwrap();
        }

        let target = ro_dir.join("trajectory.json");
        let t = sample_trajectory(target.to_string_lossy().to_string());

        let result = t.save_record();
        // Depending on platform, this could fail at file creation OR write.
        match result {
            Ok(_) => panic!("expected failure due to permissions"),
            Err(TrajectoryError::CreateFileError(_, _)) => {
                // acceptable on systems where file creation itself fails
            }
            Err(TrajectoryError::WriteError(path, msg)) => {
                assert!(path.ends_with("trajectory.json"));
                assert!(!msg.is_empty());
            }
            Err(e) => panic!("unexpected error variant: {e:?}"),
        }
    }

    fn sample_trajectory_update() -> Trajectory {
        Trajectory {
            path: "/tmp/traj.json".into(),
            start_time: "2024-01-01T00:00:00Z".into(),
            trajectory_data: Some(TrajectoryData {
                task: "initial task".into(),
                start_time: "2024-01-01T00:00:00Z".into(),
                end_time: Some("2024-01-01T01:00:00Z".into()),
                provider: "openai".into(),
                model: "gpt-4".into(),
                max_step: 5,
                llm_interaction: vec![],
                success: false,
                final_result: Some("pending".into()),
                execution_time: 3600.0,
            }),
        }
    }
    #[test]
    fn update_single_field_task() {
        let mut t = sample_trajectory_update();
        let upd = TrajectoryDataUpdate {
            task: Some("new task".into()),
            ..Default::default()
        };
        t.update_record(upd).unwrap();
        assert_eq!(t.trajectory_data.as_ref().unwrap().task, "new task");
        // Unchanged others
        assert_eq!(t.trajectory_data.as_ref().unwrap().provider, "openai");
    }
    #[test]
    fn update_multiple_fields() {
        let mut t = sample_trajectory_update();
        let upd = TrajectoryDataUpdate {
            provider: Some("anthropic".into()),
            model: Some("claude-3".into()),
            max_step: Some(42),
            success: Some(true),
            execution_time: Some(123.45),
            ..Default::default()
        };
        t.update_record(upd).unwrap();
        assert_eq!(t.trajectory_data.as_ref().unwrap().provider, "anthropic");
        assert_eq!(t.trajectory_data.as_ref().unwrap().model, "claude-3");
        assert_eq!(t.trajectory_data.as_ref().unwrap().max_step, 42);
        assert!(t.trajectory_data.as_ref().unwrap().success);
        assert!((t.trajectory_data.as_ref().unwrap().execution_time - 123.45).abs() < f64::EPSILON);
    }

    #[test]
    fn clear_final_result() {
        let mut t = sample_trajectory_update();
        // Use Some(None) to clear Option<String>
        let upd = TrajectoryDataUpdate {
            final_result: Some(None),
            ..Default::default()
        };
        t.update_record(upd).unwrap();
        assert_eq!(t.trajectory_data.as_ref().unwrap().final_result, None);
    }
    #[test]
    fn set_final_result() {
        let mut t = sample_trajectory_update();
        let upd = TrajectoryDataUpdate {
            final_result: Some(Some("done".into())),
            ..Default::default()
        };
        t.update_record(upd).unwrap();
        assert_eq!(
            t.trajectory_data.as_ref().unwrap().final_result,
            Some("done".into())
        );
    }

    #[test]
    fn reject_empty_task() {
        let mut t = sample_trajectory_update();
        let upd = TrajectoryDataUpdate {
            task: Some("   ".into()),
            ..Default::default()
        };
        let err = t.update_record(upd).unwrap_err();
        assert_eq!(
            err,
            TrajectoryError::Validation("task cannot be empty".into())
        );
    }
    #[test]
    fn reject_zero_max_step() {
        let mut t = sample_trajectory_update();
        let upd = TrajectoryDataUpdate {
            max_step: Some(0),
            ..Default::default()
        };
        let err = t.update_record(upd).unwrap_err();
        assert_eq!(
            err,
            TrajectoryError::Validation("max_step must be > 0".into())
        );
    }
    #[test]
    fn reject_negative_execution_time() {
        let mut t = sample_trajectory_update();
        let upd = TrajectoryDataUpdate {
            execution_time: Some(-0.1),
            ..Default::default()
        };
        let err = t.update_record(upd).unwrap_err();
        assert_eq!(
            err,
            TrajectoryError::Validation("execution_time cannot be negative".into())
        );
    }
    #[test]
    fn no_op_update_is_ok() {
        let mut t = sample_trajectory_update();
        let snapshot = t.trajectory_data.clone();
        let upd = TrajectoryDataUpdate::default();
        t.update_record(upd).unwrap();
        assert_eq!(t.trajectory_data, snapshot);
    }
    #[test]
    fn whitespace_trim_validation_for_provider_model() {
        let mut t = sample_trajectory_update();
        let err1 = t
            .update_record(TrajectoryDataUpdate {
                provider: Some("   ".into()),
                ..Default::default()
            })
            .unwrap_err();
        assert_eq!(
            err1,
            TrajectoryError::Validation("provider cannot be empty".into())
        );
        let err2 = t
            .update_record(TrajectoryDataUpdate {
                model: Some("\n".into()),
                ..Default::default()
            })
            .unwrap_err();
        assert_eq!(
            err2,
            TrajectoryError::Validation("model cannot be empty".into())
        );
    }
    #[test]
    fn update_end_time_and_success_together() {
        let mut t = sample_trajectory_update();
        let upd = TrajectoryDataUpdate {
            end_time: Some("2024-01-01T02:00:00Z".into()),
            success: Some(true),
            ..Default::default()
        };
        t.update_record(upd).unwrap();
        assert_eq!(
            t.trajectory_data.as_ref().unwrap().end_time,
            Some("2024-01-01T02:00:00Z".to_string())
        );
        assert!(t.trajectory_data.as_ref().unwrap().success);
    }

    #[test]
    fn write_record_creates_when_missing() {
        let dir = tempfile::tempdir().unwrap();
        let file_path = dir.path().join("nested/trajectory.json");
        let path_str = file_path.to_string_lossy().to_string();

        // Create a trajectory and set fields consistently
        let mut traj = Trajectory {
            path: path_str.clone(),
            start_time: "2024-01-01T00:00:00Z".to_string(),
            trajectory_data: Some(TrajectoryData {
                task: "".to_string(),
                start_time: "".to_string(),
                end_time: Some("2024-01-01T01:00:00Z".to_string()),
                provider: "".to_string(),
                model: "".to_string(),
                max_step: 0,
                llm_interaction: vec![],
                success: true,
                final_result: Some("done".to_string()),
                execution_time: 3.13,
            }),
        };

        // This sets task = "test-task", plus other fields
        traj.start_recording("test-task", "prov", "m1", 42);
        traj.trajectory_data.as_mut().unwrap().end_time = Some("2024-01-01T01:00:00Z".to_string()); // if needed
        traj.trajectory_data.as_mut().unwrap().execution_time = 3.13;

        // Ensure file does not exist
        assert!(!file_path.exists());

        // Write
        traj.write_record().expect("write_record should succeed");

        // Validate
        let content = std::fs::read_to_string(&file_path).unwrap();
        let v: serde_json::Value = serde_json::from_str(&content).unwrap();

        // Assert the values we actually set
        assert_eq!(v["task"], serde_json::json!("test-task"));
        assert_eq!(
            v["start_time"],
            serde_json::json!(traj.trajectory_data.as_ref().unwrap().start_time)
        );
        assert_eq!(v["end_time"], serde_json::json!("2024-01-01T01:00:00Z"));
        assert_eq!(v["provider"], serde_json::json!("prov"));
        assert_eq!(v["model"], serde_json::json!("m1"));
        assert_eq!(v["max_step"], serde_json::json!(42));
        assert_eq!(v["llm_interaction"], serde_json::json!([]));
        assert_eq!(v["success"], serde_json::json!(true));
        assert_eq!(v["final_result"], serde_json::json!("done"));
        assert_eq!(v["execution_time"], serde_json::json!(3.13));
    }

    #[test]
    fn write_record_overwrites_existing() {
        let dir = tempdir().unwrap();
        let file_path = dir.path().join("trajectory.json");
        let path_str = file_path.to_string_lossy().to_string();
        // Seed file with initial content
        fs::create_dir_all(file_path.parent().unwrap()).unwrap();
        fs::write(&file_path, br#"{"old":"data"}"#).unwrap();
        // First write
        let mut traj = sample_trajectory(path_str.clone());
        traj.trajectory_data.as_mut().unwrap().task = "first".into();
        traj.write_record()
            .expect("first write_record should succeed");
        let first_content = fs::read_to_string(&file_path).unwrap();
        assert!(first_content.contains("\"first\""));
        assert!(!first_content.contains("\"old\""));
        // Second write with different content
        traj.trajectory_data.as_mut().unwrap().task = "second".into();
        traj.write_record()
            .expect("second write_record should succeed");
        let second_content = fs::read_to_string(&file_path).unwrap();
        assert!(second_content.contains("\"second\""));
        assert!(!second_content.contains("\"first\""));
        assert!(!second_content.contains("\"old\""));
    }
}
