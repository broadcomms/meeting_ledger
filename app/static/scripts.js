document.addEventListener("DOMContentLoaded", function() {
  const searchInput = document.getElementById("searchInput");
  const statusFilter = document.getElementById("statusFilter");
  const fromDateInput = document.getElementById("fromDate");
  const toDateInput = document.getElementById("toDate");
  const filterBtn = document.getElementById("filterBtn");

  function filterMeetings() {
    const searchValue = searchInput.value.trim().toLowerCase();
    const statusValue = statusFilter.value.trim().toLowerCase();
    const fromDate = fromDateInput.value;
    const toDate = toDateInput.value;

    const meetingItems = document.querySelectorAll(".meeting-item");

      meetingItems.forEach(item => {
          const title = item.getAttribute("data-title") || "";
          const date = item.getAttribute("data-date") || "";
          const status = item.getAttribute("data-status") || "";

          let show = true;

          // Filter by search text (title or date)
          if (searchValue) {
              if (!title.includes(searchValue) && !date.includes(searchValue)) {
                  show = false;
              }
          }

          // Filter by status (ensure proper matching)
          if (statusValue && status !== statusValue) {
              show = false;
          }

          // Ensure valid date filtering
          if (fromDate && date < fromDate) {
              show = false;
          }
          if (toDate && date > toDate) {
              show = false;
          }

          // Show/hide the item based on criteria
          item.style.display = show ? "flex" : "none";
      });
  }

  if (filterBtn) {
      filterBtn.addEventListener("click", filterMeetings);
  }

  // Enable live search filtering
  if (searchInput) {
      searchInput.addEventListener("keyup", filterMeetings);
  }

  // Allow filtering as soon as dropdown is selected.
  if (statusFilter) {
      statusFilter.addEventListener("change", filterMeetings);
  }
});
