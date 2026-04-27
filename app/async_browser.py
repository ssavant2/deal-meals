"""
Async Shared Browser Manager

PURPOSE:
Manages a single async Playwright browser instance shared across multiple async tasks.
This is the CORRECT way to use Playwright for parallel scraping - NO ZOMBIES!

ARCHITECTURE:
- Main async event loop
- ONE browser instance
- Multiple concurrent tasks share the browser
- Each task gets isolated context
- Controlled shutdown → no zombies

BENEFITS:
- NO ZOMBIES (proper async cleanup!)
- Thread-safe (async is single-threaded)
- Fast (async I/O is more efficient than threads)
- Less resources (one Chrome for all tasks)
- Scalable (can run 10+ concurrent tasks easily)

USAGE:
    from async_browser import AsyncBrowserManager
    
    async def main():
        async with AsyncBrowserManager() as browser:
            # Run concurrent tasks
            tasks = [scrape_url(url, browser) for url in urls]
            results = await asyncio.gather(*tasks)
    
    asyncio.run(main())
"""

from playwright.async_api import async_playwright, Browser, BrowserContext
from loguru import logger
from typing import Optional, List
import asyncio
import os


class AsyncBrowserManager:
    """
    Async context manager for a shared Playwright browser.
    
    Example:
        async with AsyncBrowserManager() as browser:
            # Create task
            result = await scrape_with_browser(url, browser)
    """
    
    def __init__(self, headless: bool = True, slow_mo: Optional[int] = None, force_cleanup: Optional[bool] = None):
        """
        Args:
            headless: Run Chrome in headless mode (default: True)
            slow_mo: Slow down operations by N milliseconds (useful for debugging)
            force_cleanup: Use aggressive cleanup (pkill). Default: read from FORCE_BROWSER_CLEANUP env.
                          Set True in dedicated containers, False when sharing host with other Chrome users.
        """
        self.headless = headless
        self.slow_mo = slow_mo
        self.playwright = None
        self.browser: Optional[Browser] = None

        # Determine force_cleanup setting
        if force_cleanup is not None:
            self.force_cleanup = force_cleanup
        else:
            self.force_cleanup = os.getenv('FORCE_BROWSER_CLEANUP', '').lower() in ('1', 'true', 'yes')
    
    
    async def start(self) -> Browser:
        """
        Start the shared browser.
        
        Returns:
            Async Playwright Browser instance
        """
        if self.browser is not None:
            logger.warning("Browser already started, returning existing instance")
            return self.browser
        
        logger.info("🚀 Starting shared async Playwright browser...")
        
        try:
            # Start async Playwright
            self.playwright = await async_playwright().start()
            
            # Launch browser with minimal processes
            launch_options = {
                "headless": self.headless,
                "args": [
                    "--disable-dev-shm-usage",  # Use /tmp instead of /dev/shm
                    "--no-sandbox",  # Required in Docker
                    "--disable-setuid-sandbox",  # Required in Docker
                    "--disable-gpu",  # Not needed in headless
                ]
            }
            
            if self.slow_mo:
                launch_options["slow_mo"] = self.slow_mo
            
            self.browser = await self.playwright.chromium.launch(**launch_options)
            
            logger.success(f"✅ Shared async browser started (headless={self.headless})")
            return self.browser
            
        except Exception as e:
            logger.error(f"❌ Could not start browser: {e}")
            await self.stop()
            raise
    
    
    async def stop(self):
        """Stop the browser and clean up - WITH PROPER PROCESS REAPING."""
        if self.browser:
            logger.info("🛑 Stopping shared browser...")
            
            try:
                # Step 1: Wait for all pending operations to complete
                await asyncio.sleep(1)
                
                # Step 2: Close all contexts first (with retry)
                max_attempts = 3
                for attempt in range(max_attempts):
                    contexts = self.browser.contexts
                    if not contexts:
                        break
                    
                    logger.debug(f"Closing {len(contexts)} contexts (attempt {attempt + 1})")
                    
                    for context in contexts:
                        try:
                            await context.close()
                        except Exception as e:
                            logger.debug(f"Error closing context: {e}")
                    
                    # Wait for contexts to actually close
                    await asyncio.sleep(0.5)
                
                # Step 3: Get Chrome PIDs BEFORE closing browser
                chrome_pids = self._get_chrome_pids()
                logger.debug(f"Found {len(chrome_pids)} Chrome processes before close")
                
                # Step 4: Close browser
                await self.browser.close()
                
                # Step 5: WAIT for Chrome processes to actually die
                await self._wait_for_processes_to_die(chrome_pids, timeout=5)
                
                logger.success("✅ Browser stopped")
                
            except Exception as e:
                logger.error(f"❌ Error stopping browser: {e}")
            
            finally:
                self.browser = None
        
        # Stop Playwright
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception as e:
                logger.debug(f"Could not stop playwright cleanly: {e}")
            finally:
                self.playwright = None
        
        # Aggressive cleanup only if enabled (safe in dedicated containers)
        if self.force_cleanup:
            # Give kernel time to reap zombies
            await asyncio.sleep(0.5)

            # Final cleanup - kills ALL chrome processes on host!
            self._cleanup_chrome_processes()

            # Wait for kernel to finish reaping
            await asyncio.sleep(0.5)

            # Final zombie reaping attempt
            self._force_reap_zombies()
        else:
            # Just wait for orderly shutdown
            await asyncio.sleep(0.5)
    
    
    def _get_chrome_pids(self) -> List[int]:
        """Get list of current Chrome process IDs."""
        import subprocess
        try:
            result = subprocess.run(
                ["pgrep", "chrome"],
                capture_output=True,
                text=True
            )
            
            if result.stdout:
                return [int(pid) for pid in result.stdout.strip().split('\n')]
            return []
            
        except Exception as e:
            logger.debug(f"Could not get Chrome PIDs: {e}")
            return []
    
    
    async def _wait_for_processes_to_die(self, pids: List[int], timeout: float = 5):
        """
        Wait for specific processes to die (become zombies or disappear).
        If they don't die, KILL them before they become zombies.
        """
        import subprocess
        import os
        import signal
        
        start = asyncio.get_running_loop().time()

        while asyncio.get_running_loop().time() - start < timeout:
            # Check which PIDs still exist
            alive = []
            for pid in pids:
                try:
                    # Check if process exists
                    result = subprocess.run(
                        ["ps", "-p", str(pid)],
                        capture_output=True
                    )
                    
                    if result.returncode == 0:  # Process still exists
                        alive.append(pid)

                except (subprocess.SubprocessError, OSError):
                    # Process check failed, assume it's gone
                    pass
            
            if not alive:
                logger.debug("✅ All Chrome processes terminated")
                return
            
            # Wait a bit and check again
            await asyncio.sleep(0.1)
        
        # Timeout reached - force kill any survivors!
        if alive:
            logger.debug(f"⚠️  {len(alive)} Chrome processes still alive after {timeout}s - KILLING THEM!")
            
            for pid in alive:
                try:
                    # SIGKILL - no mercy!
                    os.kill(pid, signal.SIGKILL)
                    logger.debug(f"Killed Chrome process {pid}")
                except ProcessLookupError:
                    # Already dead
                    pass
                except Exception as e:
                    logger.debug(f"Could not kill {pid}: {e}")
            
            # Wait for kills to take effect
            await asyncio.sleep(0.5)
            
            # Now try to reap them as they become zombies
            for pid in alive:
                try:
                    os.waitpid(pid, os.WNOHANG)
                    logger.debug(f"Reaped killed process {pid}")
                except ChildProcessError:
                    # Process already reaped or doesn't exist
                    pass
    
    
    def _cleanup_chrome_processes(self):
        """Kill any remaining Chrome processes (backup)."""
        import subprocess
        try:
            subprocess.run(["pkill", "-9", "chrome"], check=False, capture_output=True)
            subprocess.run(["pkill", "-9", "chromium"], check=False, capture_output=True)
            logger.debug("🧹 Cleaned up Chrome processes")
        except Exception as e:
            logger.debug(f"Could not clean Chrome processes: {e}")
    
    
    def _force_reap_zombies(self):
        """Force kernel to reap zombie processes."""
        import subprocess
        import os
        try:
            # Send SIGCHLD to init (PID 1) to trigger zombie reaping
            subprocess.run(["kill", "-s", "CHLD", "1"], check=False, capture_output=True)
            
            # Try to reap any child processes of THIS process
            # This is the KEY - if we're the parent, WE need to reap!
            while True:
                try:
                    # waitpid with WNOHANG returns immediately
                    # Returns (pid, status) if child found, or (0, 0) if no children
                    pid, status = os.waitpid(-1, os.WNOHANG)
                    if pid == 0:
                        break  # No more children to reap
                    logger.debug(f"Reaped child process {pid}")
                except ChildProcessError:
                    # No child processes
                    break
                except Exception as e:
                    logger.debug(f"Error in waitpid: {e}")
                    break
                
            logger.debug("🧹 Forced zombie reaping")
        except Exception as e:
            logger.debug(f"Could not force reap: {e}")
    
    
    async def __aenter__(self) -> Browser:
        """Async context manager entry - start browser."""
        return await self.start()
    
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - stop browser."""
        await self.stop()
        return False


async def create_page_for_task(browser: Browser):
    """
    Helper function: Create isolated context and page for a task.
    
    Each async task should call this to get its own isolated environment.
    
    Args:
        browser: Shared async browser instance
        
    Returns:
        Tuple of (context, page)
        
    Example:
        async def worker(url, browser):
            context, page = await create_page_for_task(browser)
            try:
                await page.goto(url)
                # ... do work ...
            finally:
                await page.close()
                await context.close()
    """
    context = await browser.new_context()
    page = await context.new_page()
    return context, page


# === TEST FUNCTION ===
async def test_scrape(url: str, browser: Browser, task_id: int):
    """Test function that scrapes a URL."""
    try:
        context, page = await create_page_for_task(browser)
        
        await page.goto(url, timeout=10000)
        title = await page.title()
        
        logger.info(f"Task {task_id}: {title}")
        
        await page.close()
        await context.close()
        
        return f"Task {task_id} OK: {title}"
        
    except Exception as e:
        logger.error(f"Task {task_id} error: {e}")
        return None


async def main():
    """Test the async browser manager."""
    from rich.console import Console
    import subprocess
    
    console = Console()
    console.print("\n[bold blue]🧪 Testing Async Shared Browser Manager[/bold blue]\n")
    
    # Test URLs
    urls = [
        "https://www.zeta.nu/recept/pasta/",
        "https://www.zeta.nu/recept/pizza/",
        "https://www.zeta.nu/recept/risotto/",
        "https://www.zeta.nu/recept/forratt/",
        "https://www.zeta.nu/recept/dessert/",
    ]
    
    try:
        # Start shared browser
        async with AsyncBrowserManager() as browser:
            console.print("[green]✅ Browser started[/green]\n")
            
            # Run concurrent tasks
            console.print(f"[yellow]Testing with {len(urls)} concurrent tasks...[/yellow]\n")
            
            tasks = [
                test_scrape(url, browser, i)
                for i, url in enumerate(urls, 1)
            ]
            
            # Run all tasks concurrently
            results = await asyncio.gather(*tasks)
            
            # Show results
            console.print("\n[green]✅ All tasks completed[/green]")
            for result in results:
                if result:
                    console.print(f"  • {result}")
            
            # Wait a bit
            console.print("\n[yellow]Waiting 2 seconds...[/yellow]")
            await asyncio.sleep(2)
        
        # Browser closes automatically here
        console.print("\n[green]✅ Browser closed correctly![/green]\n")
        
        # Verify no Chrome processes left
        await asyncio.sleep(1)  # Give kernel time to clean up
        
        result = subprocess.run(
            ["pgrep", "-c", "chrome"],
            capture_output=True,
            text=True
        )
        
        chrome_count = int(result.stdout.strip()) if result.stdout.strip() else 0
        
        if chrome_count == 0:
            console.print("[bold green]🎉 PERFECT! No Chrome processes left![/bold green]\n")
        else:
            console.print(f"[yellow]⚠️  {chrome_count} Chrome processes remain[/yellow]\n")
            
            # Show what remains
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True
            )
            
            for line in result.stdout.split('\n'):
                if 'chrome' in line.lower():
                    console.print(f"[dim]{line}[/dim]")
        
    except Exception as e:
        console.print(f"[bold red]❌ Test failed: {e}[/bold red]\n")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run async main
    asyncio.run(main())
