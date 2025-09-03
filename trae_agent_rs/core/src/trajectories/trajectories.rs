use core::error;
use std::{alloc::System, collections::HashMap, fs, time::SystemTime};
use thiserror::Error;
use serde::Serialize;

use std::io::{self, Write};
use std::path::Path;
use std::time::{UNIX_EPOCH};

// every recorde should have CRU feature
pub trait Recorder {
    // recorder consider as the necessary implementation of any log system
    // when we want to implement other db style recorder we shd and shd only need to 
    // implement the following methods
    fn read_record();
    fn write_record();
    fn update_record();
    fn save_record(&self) -> Result<(), TrajectoryError> ;
}

pub struct Trajectory{
    pub path: String,
    pub start_time:String,
    pub trajectory_data: TrajectoryData,
}

#[derive(Serialize)]
pub struct TrajectoryData{
    pub task: String,
    pub start_time: String,
    pub end_time: String,
    pub provider: String,
    pub model: String, 
    pub max_step: u64,
    pub llm_interaction: Vec<LLMRecord>,
    pub success: bool,
    pub final_result: Option<String>,
    pub execution_time: f64,
}

#[derive(Serialize, Clone)]
pub struct LLMRecord {}


impl Trajectory {
    pub fn start_recording(
        &mut self, 
        task: &str,
        provider: &str,
        model: &str,
        max_step:u64
    ){
        self.trajectory_data.task = task.to_string();
        self.trajectory_data.start_time = system_time_to_string(&SystemTime::now());
        self.trajectory_data.max_step = max_step;
        self.trajectory_data.provider = provider.to_string();
        self.trajectory_data.model = model.to_string();
    }
}

impl Recorder for Trajectory {
    fn read_record() {}

    fn save_record(&self) -> Result<(), TrajectoryError> {
        let trajectory_path = Path::new(&self.path);
        if let Some(parent_dir) = trajectory_path.parent() {
            if let Err(e) = fs::create_dir_all(parent_dir) {
                return Err(TrajectoryError::CreateDirectoryError(
                    parent_dir.to_string_lossy().to_string(),
                    e.to_string(),
                ));
            }
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
        let serializable_data = self.trajectory_data.to_serializable(); // Using a helper method
        let json_string = match serde_json::to_string_pretty(&serializable_data) {
            Ok(json) => json,
            Err(e) => {
                return Err(TrajectoryError::SerializationError(e.to_string()));
            }
        };
        if let Err(e) = writer.write_all(json_string.as_bytes()) {
            return Err(TrajectoryError::WriteError(self.path.clone(), e.to_string()));
        }
        // If everything succeeded, return Ok.
        Ok(())
    }

    fn update_record() {}
    fn write_record() {}
}


#[derive(Error, Debug)]
pub enum TrajectoryError{
    #[error("Create File file at path:{0}. Error message: {0}")]
    CreateFileError(String, String),

    #[error("Create Directory fail at path {0}. Error message{0}")]
    CreateDirectoryError(String,String),

    #[error("Fail to serialize the data error message: {0}")]
    SerializationError(String),

    #[error("Fail to write the data to the json file to path: {0} with the error message {0}")]
    WriteError(String, String)

}



fn system_time_to_string(st: &SystemTime) -> String {
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
            max_step: self.max_step.clone(),
            llm_interaction: self.llm_interaction.clone(),
            success: self.success.clone(),
            final_result: self.final_result.clone(),
            execution_time: self.execution_time.clone(),
        }
    }
}




#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::io::Read;
    use std::path::{Path, PathBuf};
    use tempfile::TempDir;

    fn sample_trajectory(path: impl Into<String>) -> Trajectory {
        Trajectory {
            path: path.into(),
            start_time: "0".to_string(),
            trajectory_data: TrajectoryData {
                task: "test-task".to_string(),
                start_time: "1234567890".to_string(),
                end_time: "1234567899".to_string(),
                provider: "openai".to_string(),
                model: "gpt-4o".to_string(),
                max_step: 5,
                llm_interaction: vec![],
                success: true,
                final_result: Some("done".to_string()),
                execution_time: 1.23,
            },
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
        assert!(nested_dir.exists() && nested_dir.is_dir(), "parent directories should exist");
        assert!(file_path.exists() && file_path.is_file(), "file should be created");

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
        assert!(content.contains("\n"), "pretty JSON should contain newlines");
    }

    #[test]
    fn save_record_overwrites_existing_file() {
        let tmp = TempDir::new().expect("tempdir");
        let file_path = tmp.path().join("trajectory.json");

        // Prewrite a different file
        fs::create_dir_all(file_path.parent().unwrap()).unwrap();
        fs::write(&file_path, r#"{"old":"data"}"#).unwrap();

        let t = sample_trajectory(file_path.to_string_lossy().to_string());
        t.save_record().expect("save_record should succeed and overwrite");

        let content = read_to_string(&file_path);
        let v: serde_json::Value = serde_json::from_str(&content).expect("valid json");
        assert_eq!(v["task"], "test-task");
        assert!(content.contains("\n"), "still pretty printed");
        assert!(!content.contains(r#""old":"data""#), "old content should be gone");
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
        let err = t.save_record().expect_err("should fail creating directory under a file");

        // Assert: error kind
        match err {
            TrajectoryError::CreateDirectoryError(path, msg) => {
                assert!(path.contains("not_a_dir"), "path should mention failing parent");
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
                assert!(path.ends_with("trajectory.json"), "should reference the target path");
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
}
