import styles from "./SiteHeader.module.css";

export default function SiteHeader() {
  return (
    <header className={styles.header}>
      <div className={styles.identity}>
        <strong>Dementia Atlas</strong>
        <span>England</span>
      </div>

      <nav className={styles.nav} aria-label="Main navigation">
        <span>Methodology</span>
        <span>About</span>
      </nav>
    </header>
  );
}
