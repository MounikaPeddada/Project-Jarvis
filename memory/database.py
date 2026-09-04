import sqlite3
import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = "memory/jarvis_memory.db"

class DatabaseManager:
    """Manages SQLite database with connection pooling and error handling."""
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern - only one instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize database manager."""
        self.db_path = DB_PATH
        self._connection = None
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Ensure database directory exists."""
        try:
            os.makedirs("memory", exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create memory directory: {str(e)}")
            raise
    
    def get_connection(self):
        """Get a database connection with error handling."""
        try:
            if self._connection is None:
                self._connection = sqlite3.connect(
                    self.db_path,
                    timeout=5.0,  # Timeout for concurrent access
                    check_same_thread=False
                )
                self._connection.row_factory = sqlite3.Row
                logger.info("Database connection established")
            return self._connection
        except sqlite3.OperationalError as e:
            logger.error(f"Database connection failed: {str(e)}")
            raise Exception(f"❌ Database Error: {str(e)}")
    
    def close_connection(self):
        """Close database connection gracefully."""
        try:
            if self._connection:
                self._connection.close()
                self._connection = None
                logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Error closing connection: {str(e)}")
    
    def __del__(self):
        """Cleanup on object destruction."""
        self.close_connection()

def init_database():
    """Create all tables if they don't exist with indexes and constraints."""
    try:
        manager = DatabaseManager()
        conn = manager.get_connection()
        cursor = conn.cursor()
        
        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON")
        
        # Table 1: Memories (explicit facts)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact TEXT NOT NULL UNIQUE,
                category TEXT DEFAULT 'general',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories(timestamp)")
        
        # Table 2: Tasks (to-do items)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL,
                due_date TEXT,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'completed', 'cancelled')),
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date)")
        
        # Table 3: Corrections (typo → fix mappings)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bad_input TEXT NOT NULL,
                good_output TEXT NOT NULL,
                confidence REAL DEFAULT 1.0 CHECK(confidence >= 0 AND confidence <= 1),
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_corrections_bad_input ON corrections(bad_input)")
        
        # Table 4: FULL HISTORY (EVERY command, tool, result, error)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command TEXT NOT NULL,
                tool_called TEXT,
                result TEXT,
                error TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_timestamp ON history(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_tool ON history(tool_called)")
        
        conn.commit()
        logger.info("✅ Database initialized successfully with all tables and indexes!")
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise

def log_interaction(command: str, tool_called: Optional[str] = None, result: Optional[str] = None, error: Optional[str] = None):
    """
    Log every single interaction to the history table with validation.
    
    Args:
        command: User's command (required)
        tool_called: Tool name if used (optional)
        result: Tool result or response (optional)
        error: Any error message (optional)
    """
    if not isinstance(command, str) or not command.strip():
        logger.warning("Invalid command: must be non-empty string")
        return
    
    try:
        manager = DatabaseManager()
        conn = manager.get_connection()
        cursor = conn.cursor()
        
        # Validate and sanitize inputs
        command = command.strip()[:1000]  # Max 1000 chars
        tool_called = tool_called.strip()[:100] if tool_called else None
        result = result.strip()[:5000] if result else None
        error = error.strip()[:1000] if error else None
        
        cursor.execute(
            "INSERT INTO history (command, tool_called, result, error) VALUES (?, ?, ?, ?)",
            (command, tool_called, result, error)
        )
        conn.commit()
        logger.debug(f"Logged interaction: {command[:50]}...")
        
    except sqlite3.IntegrityError as e:
        logger.error(f"Database integrity error: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to log interaction: {str(e)}")

def remember(fact: str, category: str = "general") -> bool:
    """
    Save a fact to memory.
    
    Args:
        fact: The fact to remember
        category: Category for organization
    
    Returns:
        True if successful, False otherwise
    """
    if not isinstance(fact, str) or not fact.strip():
        logger.warning("Invalid fact: must be non-empty string")
        return False
    
    try:
        manager = DatabaseManager()
        conn = manager.get_connection()
        cursor = conn.cursor()
        
        fact = fact.strip()[:500]
        category = category.strip()[:50]
        
        cursor.execute(
            "INSERT INTO memories (fact, category) VALUES (?, ?)",
            (fact, category)
        )
        conn.commit()
        logger.info(f"✅ Remembered: {fact[:50]}...")
        return True
        
    except sqlite3.IntegrityError:
        logger.warning(f"Fact already exists: {fact[:50]}...")
        return False
    except Exception as e:
        logger.error(f"Failed to remember fact: {str(e)}")
        return False

def recall(category: Optional[str] = None) -> list:
    """
    Retrieve facts from memory.
    
    Args:
        category: Filter by category (optional)
    
    Returns:
        List of facts
    """
    try:
        manager = DatabaseManager()
        conn = manager.get_connection()
        cursor = conn.cursor()
        
        if category:
            cursor.execute("SELECT fact FROM memories WHERE category = ? ORDER BY timestamp DESC", (category,))
        else:
            cursor.execute("SELECT fact FROM memories ORDER BY timestamp DESC")
        
        facts = [row[0] for row in cursor.fetchall()]
        logger.debug(f"Recalled {len(facts)} facts")
        return facts
        
    except Exception as e:
        logger.error(f"Failed to recall facts: {str(e)}")
        return []

def get_history(limit: int = 100) -> list:
    """
    Get recent history entries.
    
    Args:
        limit: Max number of entries to return
    
    Returns:
        List of history entries
    """
    try:
        manager = DatabaseManager()
        conn = manager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT command, tool_called, result, error, timestamp FROM history ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
        
        return [dict(row) for row in cursor.fetchall()]
        
    except Exception as e:
        logger.error(f"Failed to get history: {str(e)}")
        return []

if __name__ == "__main__":
    init_database()
    logger.info("Database ready!")