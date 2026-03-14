const gplay = require("google-play-scraper").default;

const keyword = process.argv[2];
const maxApps = parseInt(process.argv[3]) || 5;
const reviewsPerApp = parseInt(process.argv[4]) || 50;

if (!keyword) {
  console.error("Usage: node gplay_npm.js <keyword> [maxApps] [reviewsPerApp]");
  process.exit(1);
}

async function run() {
  try {
    const apps = await gplay.search({
      term: keyword,
      num: maxApps,
      fullDetail: true,
    });

    const appsMeta = [];
    const frustrationReviews = [];
    let totalReviewsScanned = 0;

    for (const app of apps) {
      appsMeta.push({
        name: app.title,
        app_id: app.appId,
        avg_rating: app.score,
        total_ratings: app.ratings,
      });

      try {
        // Fetch a larger batch of reviews to filter for low ratings
        // Since we can't filter by score on the server, we fetch more and filter locally
        const reviews = await gplay.reviews({
          appId: app.appId,
          sort: gplay.sort.NEWEST,
          num: Math.min(reviewsPerApp * 3, 1000), // Fetch up to 1000 to find enough low ratings
        });

        const rawData = Array.isArray(reviews) ? reviews : reviews.data || [];
        totalReviewsScanned += rawData.length;

        const filtered = rawData.filter((r) => [1, 2, 3].includes(r.score));

        filtered.slice(0, reviewsPerApp).forEach((r) => {
          frustrationReviews.push({
            app_name: app.title,
            review_text: r.text,
            score: r.score,
            thumbs_up: r.thumbsUp,
            at: r.date,
          });
        });
      } catch (e) {
        // Skip if reviews fail for an app
      }
    }

    console.log(
      JSON.stringify(
        {
          source: "google_play_store_npm",
          keyword: keyword,
          apps_searched: appsMeta.length,
          total_reviews_scanned: totalReviewsScanned,
          apps: appsMeta,
          frustration_reviews: frustrationReviews,
        },
        null,
        2,
      ),
    );
  } catch (error) {
    console.error(error);
    process.exit(1);
  }
}

run();
