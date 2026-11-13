# Let Django use PyMySQL (pure-Python) as if it were the MySQLdb driver.
import pymysql

pymysql.install_as_MySQLdb()
