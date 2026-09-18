import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logging
import re
from datetime import datetime
from memory.database import DatabaseManager

logger = logging.getLogger(__name__)

VAULT_PATH = "obsidian_vault"

class ObsidianSync:
    """Syncs SQLite database to Obsidian markdown notes."""
    
    def __init__(self):
        self._ensure_vault_structure()
    
    def _ensure_vault_structure(self):
        """Create obsidian_vault folder structure if it doesn't exist."""
        try:
            os.makedirs(f"{VAULT_PATH}/Facts", exist_ok=True)
            os.makedirs(f"{VAULT_PATH}/Tasks", exist_ok=True)
            os.makedirs(f"{VAULT_PATH}/Corrections", exist_ok=True)
            os.makedirs(f"{VAULT_PATH}/History", exist_ok=True)
            logger.info("✅ Obsidian vault structure ready")
        except Exception as e:
            logger.error(f"Failed to create vault structure: {str(e)}")
    
    def sync_memories(self):
        """Sync all memories from database to markdown files (Hard Sync)."""
        try:
            manager = DatabaseManager()
            conn = manager.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT id, fact, category, timestamp FROM memories")
            memories = cursor.fetchall()
            
            self._clear_folder(f"{VAULT_PATH}/Facts")
            
            for row in memories:
                memory_id, fact, category, timestamp = row
                filename = f"{VAULT_PATH}/Facts/{memory_id}_{self._sanitize_filename(fact)}.md"
                
                content = f"""# Fact #{memory_id}

**Category:** {category}
**Learned:** {timestamp}

## Content
{fact}

---
*Last synced: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
                self._write_file(filename, content)
            
            logger.info(f"✅ Synced {len(memories)} memories to Obsidian")
        
        except Exception as e:
            logger.error(f"Failed to sync memories: {str(e)}")
    
    def sync_tasks(self):
        """Sync all tasks from database to markdown files (Hard Sync)."""
        try:
            manager = DatabaseManager()
            conn = manager.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT id, task, status, due_date, timestamp FROM tasks ORDER BY status")
            tasks = cursor.fetchall()
            
            self._clear_folder(f"{VAULT_PATH}/Tasks")
            
            for row in tasks:
                task_id, task, status, due_date, timestamp = row
                filename = f"{VAULT_PATH}/Tasks/{task_id}_{self._sanitize_filename(task)}.md"
                
                status_emoji = "✅" if status == "completed" else "❌" if status == "cancelled" else "📝"
                checkbox = "[x]" if status == "completed" else "[ ]"
                
                content = f"""# Task #{task_id} {status_emoji}

**Status:** {status}
**Due Date:** {due_date or 'No deadline'}
**Created:** {timestamp}

## Description
- {checkbox} {task}

---
*Last synced: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
                self._write_file(filename, content)
            
            logger.info(f"✅ Synced {len(tasks)} tasks to Obsidian")
        
        except Exception as e:
            logger.error(f"Failed to sync tasks: {str(e)}")
    
    def sync_corrections(self):
        """Sync corrections from database to markdown (Hard Sync)."""
        try:
            manager = DatabaseManager()
            conn = manager.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT bad_input, good_output, confidence, timestamp FROM corrections")
            corrections = cursor.fetchall()
            
            self._clear_folder(f"{VAULT_PATH}/Corrections")
            
            content = "# 🔧 Corrections Log\n\n"
            content += f"*Last synced: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n"
            content += f"**Total corrections:** {len(corrections)}\n\n---\n\n"
            
            if corrections:
                content += "| Bad Input | Corrected To | Confidence | Timestamp |\n"
                content += "| :--- | :--- | :--- | :--- |\n"
                for bad, good, confidence, timestamp in corrections:
                    content += f"| `{bad}` | `{good}` | {confidence} | {timestamp} |\n"
            else:
                content += "*No corrections yet.*\n"
            
            self._write_file(f"{VAULT_PATH}/Corrections/corrections_log.md", content)
            logger.info(f"✅ Synced {len(corrections)} corrections")
        
        except Exception as e:
            logger.error(f"Failed to sync corrections: {str(e)}")
    
    def sync_history(self):
        """Append new history entries to today's daily log file (APPEND-ONLY)."""
        try:
            manager = DatabaseManager()
            conn = manager.get_connection()
            cursor = conn.cursor()

            # Get today's date
            today = datetime.now().strftime('%Y-%m-%d')
            filename = f"{VAULT_PATH}/History/{today}.md"

            # Check what we've already logged today (avoid duplicates)
            already_logged_ids = self._get_logged_ids(filename)

            # Fetch only entries from today
            cursor.execute("""
                SELECT id, command, tool_called, result, error, timestamp 
                FROM history 
                WHERE DATE(timestamp) = ? 
                ORDER BY timestamp ASC
            """, (today,))
            today_history = cursor.fetchall()

            if not today_history:
                logger.info("📜 No new history to append today")
                return

            # Filter out already-logged entries
            new_entries = [row for row in today_history if row[0] not in already_logged_ids]

            if not new_entries:
                logger.info("📜 All today's history already logged")
                return

            # Open in APPEND mode ('a') so we never overwrite
            file_exists = os.path.exists(filename)
            with open(filename, "a", encoding="utf-8") as f:
                # If new file, add header
                if not file_exists:
                    f.write(f"# 📜 Activity Log: {today}\n\n")
                    f.write(f"*Created: {datetime.now().strftime('%H:%M:%S')}*\n\n---\n\n")

                for row in new_entries:
                    hid, command, tool_called, result, error, timestamp = row
                    status = "❌ ERROR" if error else "✅ SUCCESS"

                    f.write(f"<!-- ID: {hid} -->\n")
                    f.write(f"## {timestamp} | {status}\n\n")
                    f.write(f"**Command:** {command}\n\n")
                    f.write(f"**Tool Used:** `{tool_called or 'None'}`\n\n")
                    if result:
                        result_short = result[:500] + "..." if len(result) > 500 else result
                        f.write(f"**Result:** {result_short}\n\n")
                    if error:
                        f.write(f"**❌ Error:** {error}\n\n")
                    f.write("---\n\n")

            logger.info(f"✅ Appended {len(new_entries)} new entries to {filename}")
        
        except Exception as e:
            logger.error(f"Failed to sync history: {str(e)}")

    def _get_logged_ids(self, filename: str) -> set:
        """Read a markdown file and extract already-logged history IDs."""
        logged_ids = set()
        if not os.path.exists(filename):
            return logged_ids

        try:
             with open(filename, "r", encoding="utf-8") as f:
                for line in f:
                    # 👇 THIS IS THE REGEX LINE 👇
                    match = re.search(r'<!-- ID:\s*(\d+)\s*-->', line)
                    if match:
                        try:
                            logged_ids.add(int(match.group(1)))
                        except ValueError:
                            pass
        except Exception as e:
            logger.error(f"Failed to read logged IDs from {filename}: {str(e)}")

        return logged_ids
    
    def sync_all(self):
        """Sync everything to Obsidian."""
        logger.info("🔄 Starting Obsidian sync...")
        self.sync_memories()
        self.sync_tasks()
        self.sync_corrections()
        self.sync_history()
        logger.info("✅ Obsidian sync complete!")
    
    @staticmethod
    def _sanitize_filename(text: str) -> str:
        """Convert text to safe filename."""
        safe = "".join(c if c.isalnum() or c in "-_ " else "" for c in text)
        return safe[:50].strip().replace(" ", "_")
    
    @staticmethod
    def _clear_folder(folder_path: str):
        """Delete all files in a folder."""
        try:
            if os.path.exists(folder_path):
                for filename in os.listdir(folder_path):
                    filepath = os.path.join(folder_path, filename)
                    if os.path.isfile(filepath):
                        os.remove(filepath)
        except Exception as e:
            logger.error(f"Failed to clear folder {folder_path}: {str(e)}")
    
    @staticmethod
    def _write_file(filepath: str, content: str):
        """Write content to a file safely."""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            logger.error(f"Failed to write {filepath}: {str(e)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    syncer = ObsidianSync()
    syncer.sync_all()