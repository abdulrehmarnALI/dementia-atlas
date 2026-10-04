import styles from "./SiteFooter.module.css";

export default function SiteFooter() {
  return (
    <footer className={styles.footer}>
      <p>
        Dementia Atlas · Independent project · Data from publicly available NHS
        sources
      </p>
    </footer>
  );
}
