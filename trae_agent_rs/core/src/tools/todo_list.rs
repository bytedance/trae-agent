use crate::Tool;
use serde::{Deserialize, Serialize};
use std::{collections::HashMap, sync::Mutex};
use thiserror::Error;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum TodoStatus {
    #[serde(rename = "todo")]
    Todo,
    #[serde(rename = "in_progress")]
    InProgress,
    #[serde(rename = "done")]
    Done,
    #[serde(rename = "canceled")]
    Canceled,
    #[serde(rename = "deferred")]
    Deferred,
}

impl TodoStatus {
    fn to_emoji(&self) -> &str {
        match self {
            TodoStatus::Todo => "📋",
            TodoStatus::InProgress => "🔄",
            TodoStatus::Done => "✅",
            TodoStatus::Canceled => "❌",
            TodoStatus::Deferred => "⏸️",
        }
    }
}

impl std::str::FromStr for TodoStatus {
    type Err = TodoListError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "todo" => Ok(TodoStatus::Todo),
            "in_progress" => Ok(TodoStatus::InProgress),
            "done" => Ok(TodoStatus::Done),
            "canceled" => Ok(TodoStatus::Canceled),
            "deferred" => Ok(TodoStatus::Deferred),
            _ => Err(TodoListError::InvalidStatus(s.to_string())),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TodoItem {
    pub id: String,
    pub content: String,
    pub status: TodoStatus,
}

#[derive(Default)]
pub struct TodoList {
    items: Mutex<Vec<TodoItem>>,
    next_id: Mutex<u32>,
}

impl TodoList {
    fn generate_id(&self) -> String {
        let mut next_id = self.next_id.lock().unwrap();
        *next_id += 1;
        next_id.to_string()
    }

    fn new_todo_list(&self, items: Vec<String>) -> Result<String, TodoListError> {
        let mut todo_items = self.items.lock().unwrap();
        todo_items.clear();

        let mut next_id = self.next_id.lock().unwrap();
        *next_id = 0;
        drop(next_id);

        for content in items {
            let id = self.generate_id();
            todo_items.push(TodoItem {
                id,
                content,
                status: TodoStatus::Todo,
            });
        }

        Ok(format!(
            "Created new todo list with {} items",
            todo_items.len()
        ))
    }

    fn add_items(
        &self,
        items: Vec<String>,
        after_id: Option<String>,
    ) -> Result<String, TodoListError> {
        let mut todo_items = self.items.lock().unwrap();

        let insert_position = if let Some(id) = after_id {
            match todo_items.iter().position(|item| item.id == id) {
                Some(pos) => pos + 1,
                None => return Err(TodoListError::ItemNotFound(id)),
            }
        } else {
            todo_items.len()
        };

        let mut new_items = Vec::new();
        let items_count = items.len();
        for content in items {
            let id = self.generate_id();
            new_items.push(TodoItem {
                id,
                content,
                status: TodoStatus::Todo,
            });
        }

        for (i, item) in new_items.into_iter().enumerate() {
            todo_items.insert(insert_position + i, item);
        }

        Ok(format!("Added {} items to todo list", items_count))
    }

    fn update_item(
        &self,
        id: &str,
        new_content: Option<String>,
        new_status: Option<TodoStatus>,
    ) -> Result<String, TodoListError> {
        let mut todo_items = self.items.lock().unwrap();

        match todo_items.iter_mut().find(|item| item.id == id) {
            Some(item) => {
                let mut updates = Vec::new();

                if let Some(content) = new_content {
                    item.content = content;
                    updates.push("content");
                }

                if let Some(status) = new_status {
                    item.status = status;
                    updates.push("status");
                }

                if updates.is_empty() {
                    return Err(TodoListError::NoUpdateProvided);
                }

                Ok(format!(
                    "Updated {} for item '{}'",
                    updates.join(" and "),
                    id
                ))
            }
            None => Err(TodoListError::ItemNotFound(id.to_string())),
        }
    }

    fn delete_item(&self, id: &str) -> Result<String, TodoListError> {
        let mut todo_items = self.items.lock().unwrap();

        match todo_items.iter().position(|item| item.id == id) {
            Some(pos) => {
                todo_items.remove(pos);
                Ok(format!("Deleted item '{}'", id))
            }
            None => Err(TodoListError::ItemNotFound(id.to_string())),
        }
    }

    fn display(&self) -> String {
        let todo_items = self.items.lock().unwrap();

        if todo_items.is_empty() {
            return "Todo list is empty".to_string();
        }

        let mut result = String::new();
        result.push_str("# Todo List\n\n");

        for item in todo_items.iter() {
            result.push_str(&format!(
                "* {} {} (ID: {})\n",
                item.status.to_emoji(),
                item.content,
                item.id
            ));
        }

        result
    }
}

impl Tool for TodoList {
    fn get_name(&self) -> &str {
        "todo_list"
    }

    fn reset(&mut self) {
        let mut items = self.items.lock().unwrap();
        items.clear();
        let mut next_id = self.next_id.lock().unwrap();
        *next_id = 0;
    }

    fn get_description(&self) -> &str {
        "Manage todo lists for agents to plan and track tasks. Supports creating, adding, updating, deleting items and displaying the list.

        Subcommands:
        * `new` - Create a new todo list with initial items (all start as 'todo' status)
        * `add_items` - Add new items to the list, optionally after a specific item ID
        * `update_item` - Update the content and/or status of an existing item (at least one of content or status must be provided)
        * `delete_item` - Remove an item from the list
        * `display` - Show the todo list in markdown format with status emojis"
    }

    fn get_input_schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The command to execute",
                    "enum": ["new", "add_items", "update_item", "delete_item", "display"]
                },
                "items": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "List of todo items (for new and add_items commands)"
                },
                "id": {
                    "type": "string",
                    "description": "Item ID for update_item, delete_item commands, or after which to insert for add_items. The ID is 1-based."
                },
                "content": {
                    "type": "string",
                    "description": "New content for the todo item (for update_item command)"
                },
                "status": {
                    "type": "string",
                    "description": "New status for the todo item (for update_item command)",
                    "enum": ["todo", "in_progress", "done", "canceled", "deferred"]
                }
            },
            "required": ["command"]
        })
    }

    fn get_descriptive_message(&self, arguments: &HashMap<String, serde_json::Value>) -> String {
        let subcommand = arguments
            .get("command")
            .and_then(|x| x.as_str())
            .unwrap_or("");
        match subcommand {
            "new" => "Create new todo list".to_string(),
            "add_items" => "Add items to todo list".to_string(),
            "update_item" => "Update todo item content and/or status".to_string(),
            "delete_item" => "Delete todo item".to_string(),
            "display" => "Display todo list".to_string(),
            _ => "Todo list operation".to_string(),
        }
    }

    fn needs_approval(&self, _arguments: &HashMap<String, serde_json::Value>) -> bool {
        false
    }

    fn execute(
        &mut self,
        arguments: HashMap<String, serde_json::Value>,
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<String, String>> + Send + '_>>
    {
        Box::pin(async move {
            let subcommand = arguments
                .get("command")
                .and_then(|v| v.as_str())
                .unwrap_or("");

            match subcommand {
                "new" => {
                    let items = arguments
                        .get("items")
                        .and_then(|v| v.as_array())
                        .map(|arr| {
                            arr.iter()
                                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                                .collect()
                        })
                        .unwrap_or_default();
                    self.new_todo_list(items).map_err(|e| e.to_string())
                }
                "add_items" => {
                    let items = arguments
                        .get("items")
                        .and_then(|v| v.as_array())
                        .map(|arr| {
                            arr.iter()
                                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                                .collect()
                        })
                        .unwrap_or_default();
                    let after_id = arguments
                        .get("id")
                        .and_then(|v| v.as_str())
                        .map(|s| s.to_string());
                    self.add_items(items, after_id).map_err(|e| e.to_string())
                }
                "update_item" => {
                    let id = arguments.get("id").and_then(|v| v.as_str()).unwrap_or("");
                    let content = arguments
                        .get("content")
                        .and_then(|v| v.as_str())
                        .map(|s| s.to_string());
                    let status_str = arguments.get("status").and_then(|v| v.as_str());

                    if id.is_empty() {
                        return Err("ID parameter is required for update_item".to_string());
                    }

                    let status = if let Some(status_str) = status_str {
                        match status_str.parse::<TodoStatus>() {
                            Ok(status) => Some(status),
                            Err(e) => return Err(e.to_string()),
                        }
                    } else {
                        None
                    };

                    if content.is_none() && status.is_none() {
                        return Err("At least one of 'content' or 'status' parameter is required for update_item".to_string());
                    }

                    self.update_item(id, content, status)
                        .map_err(|e| e.to_string())
                }
                "delete_item" => {
                    let id = arguments.get("id").and_then(|v| v.as_str()).unwrap_or("");

                    if id.is_empty() {
                        return Err("ID parameter is required for delete_item".to_string());
                    }

                    self.delete_item(id).map_err(|e| e.to_string())
                }
                "display" => Ok(self.display()),
                _ => Err(format!(
                    "Unknown command: {}. Supported commands are: new, add_items, update_item, delete_item, display",
                    subcommand
                )),
            }
        })
    }
}

#[derive(Error, Debug)]
pub enum TodoListError {
    #[error("Item with ID '{0}' not found")]
    ItemNotFound(String),

    #[error(
        "Invalid status: '{0}'. Valid statuses are: todo, in_progress, done, canceled, deferred"
    )]
    InvalidStatus(String),

    #[error("At least one of content or status must be provided for update")]
    NoUpdateProvided,
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    async fn get_todo_list(num_items: usize) -> TodoList {
        let mut todo_list = TodoList::default();
        let mut args = HashMap::new();
        args.insert("command".to_string(), json!("new"));
        let mut items = Vec::new();
        for i in 0..num_items {
            items.push(format!("Item {}", i));
        }
        args.insert("items".to_string(), json!(items));
        _ = todo_list.execute(args).await;
        todo_list
    }

    #[tokio::test]
    async fn test_todo_list_new_1_item() {
        let mut todo_list = TodoList::default();
        let mut args = HashMap::new();
        args.insert("command".to_string(), json!("new"));
        args.insert("items".to_string(), json!(["Item 1".to_string()]));
        let result = todo_list.execute(args).await;
        assert_eq!(result.unwrap(), "Created new todo list with 1 items");
        assert_eq!(todo_list.items.lock().unwrap().len(), 1);
        assert_eq!(todo_list.items.lock().unwrap()[0].content, "Item 1");
    }

    #[tokio::test]
    async fn test_todo_list_new_2_items() {
        let mut todo_list = TodoList::default();
        let mut args = HashMap::new();
        args.insert("command".to_string(), json!("new"));
        args.insert(
            "items".to_string(),
            json!(["Item 1".to_string(), "Item 2".to_string()]),
        );
        let result = todo_list.execute(args).await;
        assert_eq!(result.unwrap(), "Created new todo list with 2 items");
        assert_eq!(todo_list.items.lock().unwrap().len(), 2);
        assert_eq!(todo_list.items.lock().unwrap()[0].content, "Item 1");
        assert_eq!(todo_list.items.lock().unwrap()[1].content, "Item 2");
    }

    #[tokio::test]
    async fn test_todo_list_add_items() {
        let mut todo_list = get_todo_list(2).await;
        let mut args = HashMap::new();
        args.insert("command".to_string(), json!("add_items"));
        args.insert(
            "items".to_string(),
            json!(["added_item_1".to_string(), "added_item_2".to_string()]),
        );
        args.insert("id".to_string(), json!("1"));
        let result = todo_list.execute(args).await;
        assert_eq!(result.unwrap(), "Added 2 items to todo list");
        assert_eq!(todo_list.items.lock().unwrap().len(), 4);
        assert_eq!(todo_list.items.lock().unwrap()[0].content, "Item 0");
        assert_eq!(todo_list.items.lock().unwrap()[1].content, "added_item_1");
        assert_eq!(todo_list.items.lock().unwrap()[2].content, "added_item_2");
        assert_eq!(todo_list.items.lock().unwrap()[3].content, "Item 1");
    }

    #[tokio::test]
    async fn test_todo_list_update_item() {
        let mut todo_list = get_todo_list(1).await;
        let mut args = HashMap::new();
        args.insert("command".to_string(), json!("update_item"));
        args.insert("id".to_string(), json!("1"));
        args.insert("content".to_string(), json!("updated_item_1".to_string()));
        let result = todo_list.execute(args).await;
        assert_eq!(result.unwrap(), "Updated content for item '1'");
        assert_eq!(todo_list.items.lock().unwrap()[0].content, "updated_item_1");
    }

    #[tokio::test]
    async fn test_todo_list_intial_status() {
        let todo_list = get_todo_list(1).await;
        assert_eq!(todo_list.items.lock().unwrap()[0].status, TodoStatus::Todo);
    }

    #[tokio::test]
    async fn test_todo_list_update_status() {
        let mut todo_list = get_todo_list(1).await;
        let mut args = HashMap::new();
        args.insert("command".to_string(), json!("update_item"));
        args.insert("id".to_string(), json!("1"));
        args.insert("status".to_string(), json!("in_progress".to_string()));
        let result = todo_list.execute(args).await;
        assert_eq!(result.unwrap(), "Updated status for item '1'");
        assert_eq!(
            todo_list.items.lock().unwrap()[0].status,
            TodoStatus::InProgress
        );
    }

    #[tokio::test]
    async fn test_todo_list_delete_item() {
        let mut todo_list = get_todo_list(1).await;
        let mut args = HashMap::new();
        args.insert("command".to_string(), json!("delete_item"));
        args.insert("id".to_string(), json!("1"));
        let result = todo_list.execute(args).await;
        assert_eq!(result.unwrap(), "Deleted item '1'");
        assert_eq!(todo_list.items.lock().unwrap().len(), 0);
    }

    #[tokio::test]
    async fn test_todo_list_display() {
        let todo_list = get_todo_list(1).await;
        let result = todo_list.display();
        println!("{}", result);
        assert!(result.contains("Item 0"));
    }
}
