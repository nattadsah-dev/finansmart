from os import link
from tkinter import EXCEPTION

from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_mysqldb import MySQL
from flask_mail import Mail, Message
import MySQLdb.cursors
import hashlib
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'finansmart_secret_key'

import os

app.config['MYSQL_HOST'] = os.environ.get('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER'] = os.environ.get('MYSQL_USER', 'root')
app.config['MYSQL_PASSWORD'] = os.environ.get('MYSQL_PASSWORD', '')
app.config['MYSQL_DB'] = os.environ.get('MYSQL_DB', 'finansmart')
app.config['MYSQL_PORT'] = int(os.environ.get('MYSQL_PORT', 3306))

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'rroceana@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'curmzyawtlapqcyn')
app.config['MAIL_DEFAULT_SENDER'] = ('FinanSmart', os.environ.get('MAIL_USERNAME', 'rroceana@gmail.com'))

app.secret_key = os.environ.get('SECRET_KEY', 'finansmart_secret_key')

mysql = MySQL(app)
def cek_mahasiswa():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    if session.get('role') == 'orangtua':
        return redirect(url_for('dashboard_orangtua'))
    return None
mail = Mail(app)

def cek_dan_buat_notifikasi(user_id):
    try:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
        user = cursor.fetchone()

        kategori_anggaran = {
            'Makanan & Minuman': float(user['anggaran_makan'] or 0),
            'Transportasi': float(user['anggaran_transportasi'] or 0),
            'Pendidikan': float(user['anggaran_pendidikan'] or 0),
            'Komunikasi': float(user['anggaran_komunikasi'] or 0),
            'Hiburan': float(user['anggaran_hiburan'] or 0),
            'Kesehatan': float(user['anggaran_kesehatan'] or 0),
            'Kebutuhan Pribadi': float(user['anggaran_pribadi'] or 0),
            'Lain-lain': float(user['anggaran_lainnya'] or 0),
        }

        cursor.execute('''
            SELECT c.nama, SUM(e.jumlah) as total
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            WHERE e.user_id = %s
            AND MONTH(e.tanggal) = MONTH(CURDATE())
            AND YEAR(e.tanggal) = YEAR(CURDATE())
            GROUP BY c.nama
        ''', (user_id,))
        pengeluaran = cursor.fetchall()

        for p in pengeluaran:
            nama_kategori = p['nama']
            total_keluar = float(p['total'])
            batas = kategori_anggaran.get(nama_kategori, 0)

            if batas <= 0:
                continue

            persen = (total_keluar / batas) * 100

            cursor.execute('''
                SELECT id FROM notifikasi
                WHERE user_id = %s
                AND judul LIKE %s
                AND DATE(created_at) = CURDATE()
            ''', (user_id, f'%{nama_kategori}%'))
            sudah_ada = cursor.fetchone()

            if sudah_ada:
                continue

            if persen >= 100:
                cursor.execute('''
                    INSERT INTO notifikasi (user_id, judul, pesan, tipe)
                    VALUES (%s, %s, %s, 'bahaya')
                ''', (
                    user_id,
                    f'Anggaran {nama_kategori} Terlampaui!',
                    f'Pengeluaran {nama_kategori} bulan ini Rp {total_keluar:,.0f} '
                    f'melebihi anggaran Rp {batas:,.0f}.'
                ))
            elif persen >= 80:
                cursor.execute('''
                    INSERT INTO notifikasi (user_id, judul, pesan, tipe)
                    VALUES (%s, %s, %s, 'peringatan')
                ''', (
                    user_id,
                    f'Anggaran {nama_kategori} Hampir Habis',
                    f'Pengeluaran {nama_kategori} sudah {persen:.0f}% '
                    f'dari anggaran Rp {batas:,.0f}.'
                ))

        mysql.connection.commit()
    except Exception as e:
        print(f'Error cek notifikasi: {e}')


def ambil_notifikasi(user_id):
    try:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('''
            SELECT * FROM notifikasi
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 10
        ''', (user_id,))
        return cursor.fetchall()
    except:
        return []


def hitung_notifikasi_belum_dibaca(user_id):
    try:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('''
            SELECT COUNT(*) as total FROM notifikasi
            WHERE user_id = %s AND sudah_dibaca = 0
        ''', (user_id,))
        return cursor.fetchone()['total']
    except:
        return 0


def kirim_email_reminder(email, nama):
    try:
        msg = Message(
            subject='[FinanSmart] Jangan Lupa Catat Transaksi Hari Ini!',
            recipients=[email]
        )
        msg.html = f'''
        <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto;">
            <div style="background: #1a7a4a; padding: 24px; border-radius: 12px 12px 0 0; text-align: center;">
                <h2 style="color: white; margin: 0;">FinanSmart</h2>
                <p style="color: rgba(255,255,255,0.8); margin: 4px 0 0 0; font-size: 14px;">
                    Aplikasi Manajemen Keuangan Mahasiswa
                </p>
            </div>
            <div style="background: #f9f9f9; padding: 32px; border-radius: 0 0 12px 12px;">
                <h3 style="color: #0f1f17;">Halo, {nama}!</h3>
                <p style="color: #444; line-height: 1.6;">
                    Ini adalah pengingat harianmu untuk mencatat transaksi keuangan hari ini.
                    Mencatat secara rutin membantu kamu memahami pola pengeluaran dan
                    menjaga kesehatan finansialmu.
                </p>
                <div style="background: white; border-left: 4px solid #1a7a4a;
                            padding: 16px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 0; color: #1a7a4a; font-weight: bold;">Tips Hari Ini</p>
                    <p style="margin: 8px 0 0 0; color: #444; font-size: 14px;">
                        Catat setiap pengeluaran sekecil apapun — pengeluaran kecil
                        yang tidak tercatat sering menjadi penyebab utama kebocoran
                        keuangan tanpa disadari.
                    </p>
                </div>
                <div style="text-align: center; margin-top: 24px;">
                    <a href="http://localhost:5000/transaksi"
                       style="background: #1a7a4a; color: white; padding: 12px 28px;
                              border-radius: 8px; text-decoration: none;
                              font-weight: bold; display: inline-block;">
                        Catat Transaksi Sekarang
                    </a>
                </div>
                <p style="color: #999; font-size: 12px; text-align: center; margin-top: 24px;">
                    Email ini dikirim otomatis oleh FinanSmart.
                </p>
            </div>
        </div>
        '''
        mail.send(msg)
        return True
    except Exception as e:
        print(f'Gagal kirim email: {e}')
        return False
    
def update_jejak_finansial(user_id):
    try:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('''
                       INSERT IGNORE INTO jejak_finansial (user_id, tanggal)
                       VALUES (%s, CURDATE())
                       ''', (user_id,))
        mysql.connection.commit()
    except Exception as e:
        print(f'Error update jejak finansial: {e}')

def hitung_jejak_finansial(user_id):
    try:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor. execute('''
                        SELECT tanggal FROM jejak_finansial
                        WHERE user_id = %s
                        ORDER BY tanggal DESC
                        ''', (user_id,))
        rows = cursor.fetchall()

        if not rows:
            return 0
        
        from datetime import date, timedelta
        hari_ini = date.today()
        streak = 0

        for i, row in enumerate(rows):
            tanggal = row['tanggal']
            if isinstance(tanggal, str):
                tanggal = datetime.strptime(tanggal, '%Y-%m-%d').date()
                if tanggal == expected:
                    streak += 1
                else:
                    break

        return streak
    except Exception as e:
        print(f'Error hitung jejak: {e}')
        return 0        
    
@app.context_processor
def inject_globals():
    notif_count = 0
    try:
        if 'user_id' in session:
            notif_count = hitung_notifikasi_belum_dibaca(session['user_id'])
    except:
        notif_count = 0
    return dict(request=request, notif_count=notif_count)

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' in session:
        if session.get('role') == 'orangtua':
            return redirect(url_for('dashboard_orangtua'))
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form['email']
        password = hashlib.md5(request.form['password'].encode()).hexdigest()

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s AND password = %s',
                       (email, password))
        user = cursor.fetchone()

        if user:
            session['user_id'] = user['id']
            session['nama'] = user['nama_lengkap']
            session['role'] = user['role']

            if user['role'] == 'orangtua':
                return redirect(url_for('dashboard_orangtua'))
            else:
                return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Email atau password salah!')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nama = request.form['nama']
        email = request.form['email']
        password = hashlib.md5(request.form['password'].encode()).hexdigest()
        universitas = request.form.get('universitas', '')

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        existing = cursor.fetchone()

        if existing:
            return render_template('register.html', error='Email sudah terdaftar!')
        role = request.form.get('role', 'mahasiswa')
        cursor.execute('''
            INSERT INTO users (nama_lengkap, email, password, universitas, role)
            VALUES (%s, %s, %s, %s, %s)
        ''', (nama, email, password, universitas, role))
        mysql.connection.commit()
        return redirect(url_for('index'))

    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user_id = session['user_id']
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    cursor.execute('''
        SELECT COUNT(*) as total FROM (
            SELECT id FROM income
            WHERE user_id = %s AND DATE(created_at) = CURDATE()
            UNION ALL
            SELECT id FROM expenses
            WHERE user_id = %s AND DATE(created_at) = CURDATE()
        ) as hari_ini
    ''', (user_id, user_id))
    sudah_catat = cursor.fetchone()['total']

    if sudah_catat == 0:
        cursor.execute('''
            SELECT id FROM notifikasi
            WHERE user_id = %s
            AND judul LIKE %s
            AND DATE(created_at) = CURDATE()
        ''', (user_id, '%Reminder%'))
        sudah_reminder = cursor.fetchone()

        if not sudah_reminder:
            cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
            user_data = cursor.fetchone()
            kirim_email_reminder(user_data['email'], user_data['nama_lengkap'])
            cursor.execute('''
                INSERT INTO notifikasi (user_id, judul, pesan, tipe)
                VALUES (%s, %s, %s, 'info')
            ''', (
                user_id,
                'Reminder Harian Terkirim',
                'Email reminder untuk mencatat transaksi hari ini sudah dikirim.'
            ))
            mysql.connection.commit()

    cursor.execute('''
        SELECT COALESCE(SUM(jumlah), 0) as total FROM income
        WHERE user_id = %s
        AND MONTH(tanggal) = MONTH(CURDATE())
        AND YEAR(tanggal) = YEAR(CURDATE())
    ''', (user_id,))
    total_pemasukan = cursor.fetchone()['total']

    cursor.execute('''
        SELECT COALESCE(SUM(jumlah), 0) as total FROM expenses
        WHERE user_id = %s
        AND MONTH(tanggal) = MONTH(CURDATE())
        AND YEAR(tanggal) = YEAR(CURDATE())
    ''', (user_id,))
    total_pengeluaran = cursor.fetchone()['total']

    saldo = total_pemasukan - total_pengeluaran

    if total_pemasukan > 0:
        persen_tabungan = (saldo / total_pemasukan) * 100
        fhs = min(100, max(0, round(persen_tabungan)))
    else:
        fhs = 0

    cursor.execute('''
        SELECT e.jumlah, e.tanggal, e.keterangan, c.nama as kategori
        FROM expenses e
        LEFT JOIN categories c ON e.category_id = c.id
        WHERE e.user_id = %s
        ORDER BY e.tanggal DESC, e.created_at DESC
        LIMIT 5
    ''', (user_id,))
    transaksi = cursor.fetchall()

    jejak = hitung_jejak_finansial(user_id)

    return render_template('dashboard.html',
        nama=session['nama'],
        total_pemasukan=total_pemasukan,
        total_pengeluaran=total_pengeluaran,
        saldo=saldo,
        fhs=fhs,
        transaksi=transaksi,
        jejak=jejak
    )

@app.route('/transaksi')
def transaksi():
    cek = cek_mahasiswa()
    if cek: return
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user_id = session['user_id']
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    sekarang = datetime.now()
    bulan = int(request.args.get('bulan', sekarang.month))
    tahun = int(request.args.get('tahun', sekarang.year))

    cursor.execute('''
        SELECT * FROM categories
        WHERE is_default = 1 OR user_id = %s
    ''', (user_id,))
    kategori = cursor.fetchall()

    cursor.execute('''
        SELECT jumlah, tanggal, keterangan, sumber as kategori,
               'pemasukan' as jenis
        FROM income
        WHERE user_id = %s
        AND MONTH(tanggal) = %s AND YEAR(tanggal) = %s
        UNION ALL
        SELECT e.jumlah, e.tanggal, e.keterangan, c.nama as kategori,
               'pengeluaran' as jenis
        FROM expenses e
        LEFT JOIN categories c ON e.category_id = c.id
        WHERE e.user_id = %s
        AND MONTH(e.tanggal) = %s AND YEAR(e.tanggal) = %s
        ORDER BY tanggal DESC
    ''', (user_id, bulan, tahun, user_id, bulan, tahun))
    riwayat = cursor.fetchall()

    bulan_list = [
        {'num': 1,  'nama': 'Januari'},
        {'num': 2,  'nama': 'Februari'},
        {'num': 3,  'nama': 'Maret'},
        {'num': 4,  'nama': 'April'},
        {'num': 5,  'nama': 'Mei'},
        {'num': 6,  'nama': 'Juni'},
        {'num': 7,  'nama': 'Juli'},
        {'num': 8,  'nama': 'Agustus'},
        {'num': 9,  'nama': 'September'},
        {'num': 10, 'nama': 'Oktober'},
        {'num': 11, 'nama': 'November'},
        {'num': 12, 'nama': 'Desember'},
    ]
    tahun_list = list(range(sekarang.year, sekarang.year - 3, -1))

    return render_template('transaksi.html',
        nama=session['nama'],
        kategori=kategori,
        riwayat=riwayat,
        bulan_aktif=bulan,
        tahun_aktif=tahun,
        bulan_list=bulan_list,
        tahun_list=tahun_list
    )


@app.route('/transaksi/tambah', methods=['POST'])
def tambah_transaksi():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user_id = session['user_id']
    jenis = request.form['jenis']
    jumlah = request.form['jumlah']
    tanggal = request.form['tanggal']
    keterangan = request.form.get('keterangan', '')

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if jenis == 'pengeluaran':
        category_id = request.form['category_id']
        cursor.execute('''
            INSERT INTO expenses (user_id, category_id, jumlah, tanggal, keterangan)
            VALUES (%s, %s, %s, %s, %s)
        ''', (user_id, category_id, jumlah, tanggal, keterangan))
    else:
        sumber = request.form.get('sumber', '')
        cursor.execute('''
            INSERT INTO income (user_id, jumlah, sumber, tanggal, keterangan)
            VALUES (%s, %s, %s, %s, %s)
        ''', (user_id, jumlah, sumber, tanggal, keterangan))

    mysql.connection.commit()
    cek_dan_buat_notifikasi(user_id)
    update_jejak_finansial(user_id)
    return redirect(url_for('transaksi'))

@app.route('/analisis')
def analisis():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user_id = session['user_id']
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    cursor.execute('''
        SELECT c.nama, SUM(e.jumlah) as total
        FROM expenses e
        JOIN categories c ON e.category_id = c.id
        WHERE e.user_id = %s
        AND MONTH(e.tanggal) = MONTH(CURDATE())
        AND YEAR(e.tanggal) = YEAR(CURDATE())
        GROUP BY c.nama
    ''', (user_id,))
    pie_rows = cursor.fetchall()
    pie_labels = [r['nama'] for r in pie_rows]
    pie_data = [float(r['total']) for r in pie_rows]

    kategori_terbesar = pie_labels[pie_data.index(max(pie_data))] if pie_data else '-'

    cursor.execute('''
        SELECT COALESCE(SUM(jumlah), 0) as total, COUNT(DISTINCT tanggal) as hari
        FROM expenses
        WHERE user_id = %s
        AND MONTH(tanggal) = MONTH(CURDATE())
        AND YEAR(tanggal) = YEAR(CURDATE())
    ''', (user_id,))
    row = cursor.fetchone()
    rata_harian = round(float(row['total']) / row['hari']) if row['hari'] > 0 else 0

    cursor.execute('''
        SELECT COALESCE(SUM(jumlah), 0) as total FROM income
        WHERE user_id = %s
        AND MONTH(tanggal) = MONTH(CURDATE())
        AND YEAR(tanggal) = YEAR(CURDATE())
    ''', (user_id,))
    total_masuk = float(cursor.fetchone()['total'])

    cursor.execute('''
        SELECT COALESCE(SUM(jumlah), 0) as total FROM expenses
        WHERE user_id = %s
        AND MONTH(tanggal) = MONTH(CURDATE())
        AND YEAR(tanggal) = YEAR(CURDATE())
    ''', (user_id,))
    total_keluar = float(cursor.fetchone()['total'])

    persen_tabungan = round(
        ((total_masuk - total_keluar) / total_masuk) * 100
    ) if total_masuk > 0 else 0

    cursor.execute('''
        SELECT MONTH(tanggal) as bln, SUM(jumlah) as total
        FROM income WHERE user_id = %s
        AND tanggal >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)
        GROUP BY MONTH(tanggal) ORDER BY bln
    ''', (user_id,))
    inc_rows = {r['bln']: float(r['total']) for r in cursor.fetchall()}

    cursor.execute('''
        SELECT MONTH(tanggal) as bln, SUM(jumlah) as total
        FROM expenses WHERE user_id = %s
        AND tanggal >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)
        GROUP BY MONTH(tanggal) ORDER BY bln
    ''', (user_id,))
    exp_rows = {r['bln']: float(r['total']) for r in cursor.fetchall()}

    bulan_names = ['Jan','Feb','Mar','Apr','Mei','Jun',
                   'Jul','Agu','Sep','Okt','Nov','Des']
    all_months = sorted(set(list(inc_rows.keys()) + list(exp_rows.keys())))
    bar_labels = [bulan_names[m-1] for m in all_months]
    bar_pemasukan = [inc_rows.get(m, 0) for m in all_months]
    bar_pengeluaran = [exp_rows.get(m, 0) for m in all_months]

    cursor.execute('''
        SELECT tanggal, SUM(jumlah) as total
        FROM expenses WHERE user_id = %s
        AND MONTH(tanggal) = MONTH(CURDATE())
        AND YEAR(tanggal) = YEAR(CURDATE())
        GROUP BY tanggal ORDER BY tanggal
    ''', (user_id,))
    tren_rows = cursor.fetchall()
    tren_labels = [str(r['tanggal']) for r in tren_rows]
    tren_data = [float(r['total']) for r in tren_rows]

    return render_template('analisis.html',
        nama=session['nama'],
        pie_labels=pie_labels,
        pie_data=pie_data,
        rata_harian=rata_harian,
        persen_tabungan=persen_tabungan,
        kategori_terbesar=kategori_terbesar,
        bar_labels=bar_labels,
        bar_pemasukan=bar_pemasukan,
        bar_pengeluaran=bar_pengeluaran,
        tren_labels=tren_labels,
        tren_data=tren_data
    )

@app.route('/profil')
def profil():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user_id = session['user_id']
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    user = cursor.fetchone()

    cursor.execute('''
        SELECT COUNT(*) as total FROM (
            SELECT id FROM income WHERE user_id = %s
            UNION ALL
            SELECT id FROM expenses WHERE user_id = %s
        ) as semua
    ''', (user_id, user_id))
    total_transaksi = cursor.fetchone()['total']

    hari_bergabung = (datetime.now() - user['created_at']).days + 1
    success = request.args.get('success')
    pesan = 'Perubahan berhasil disimpan!' if success else None

    return render_template('profil.html',
        user=user,
        total_transaksi=total_transaksi,
        hari_bergabung=hari_bergabung,
        success=pesan
    )


@app.route('/profil/update', methods=['POST'])
def update_profil():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user_id = session['user_id']
    jenis = request.form['jenis']
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if jenis == 'profil':
        nama = request.form['nama']
        universitas = request.form.get('universitas', '')
        password_baru = request.form.get('password_baru', '')
        konfirmasi = request.form.get('konfirmasi_password', '')

        if password_baru:
            if password_baru != konfirmasi:
                cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
                user = cursor.fetchone()
                return render_template('profil.html', user=user,
                    error='Konfirmasi password tidak cocok!')
            password_hash = hashlib.md5(password_baru.encode()).hexdigest()
            cursor.execute('''
                UPDATE users SET nama_lengkap=%s, universitas=%s, password=%s
                WHERE id = %s
            ''', (nama, universitas, password_hash, user_id))
        else:
            cursor.execute('''
                UPDATE users SET nama_lengkap=%s, universitas=%s
                WHERE id = %s
            ''', (nama, universitas, user_id))

        session['nama'] = nama

    elif jenis == 'anggaran':
        cursor.execute('''
            UPDATE users SET
                anggaran_makan=%s, anggaran_transportasi=%s,
                anggaran_pendidikan=%s, anggaran_komunikasi=%s,
                anggaran_hiburan=%s, anggaran_kesehatan=%s,
                anggaran_pribadi=%s, anggaran_lainnya=%s
            WHERE id = %s
        ''', (
            request.form.get('anggaran_makan', 0),
            request.form.get('anggaran_transportasi', 0),
            request.form.get('anggaran_pendidikan', 0),
            request.form.get('anggaran_komunikasi', 0),
            request.form.get('anggaran_hiburan', 0),
            request.form.get('anggaran_kesehatan', 0),
            request.form.get('anggaran_pribadi', 0),
            request.form.get('anggaran_lainnya', 0),
            user_id
        ))

    mysql.connection.commit()
    return redirect(url_for('profil') + '?success=1')

@app.route('/notifikasi')
def notifikasi():
    if 'user_id' not in session:
        return jsonify({'notifikasi': [], 'status': 'unauthorized'})
    notif = ambil_notifikasi(session['user_id'])
    hasil = []
    for n in notif:
        hasil.append({
            'id': n['id'],
            'judul': n['judul'],
            'pesan': n['pesan'],
            'tipe': n['tipe'],
            'sudah_dibaca': n['sudah_dibaca'],
            'created_at': str(n['created_at'])
        })
    return jsonify({'notifikasi': hasil, 'status': 'ok'})


@app.route('/notifikasi/baca-semua')
def baca_semua_notifikasi():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''
        UPDATE notifikasi SET sudah_dibaca = 1
        WHERE user_id = %s
    ''', (session['user_id'],))
    mysql.connection.commit()
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/kirim-reminder')
def kirim_reminder():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user_id = session['user_id']
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    user = cursor.fetchone()

    cursor.execute('''
        SELECT COUNT(*) as total FROM (
            SELECT id FROM income
            WHERE user_id = %s AND DATE(created_at) = CURDATE()
            UNION ALL
            SELECT id FROM expenses
            WHERE user_id = %s AND DATE(created_at) = CURDATE()
        ) as hari_ini
    ''', (user_id, user_id))
    sudah_catat = cursor.fetchone()['total']

    if sudah_catat > 0:
        return jsonify({
            'status': 'skip',
            'pesan': 'Kamu sudah mencatat transaksi hari ini!'
        })

    hasil = kirim_email_reminder(user['email'], user['nama_lengkap'])

    if hasil:
        return jsonify({
            'status': 'ok',
            'pesan': f'Reminder berhasil dikirim ke {user["email"]}'
        })
    else:
        return jsonify({
            'status': 'error',
            'pesan': 'Gagal mengirim email. Cek konfigurasi email.'
        })

@app.route('/tantangan')
def tantangan():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user_id = session['user_id']
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    from datetime import date, timedelta

    cursor.execute('''
        SELECT * FROM categories
        WHERE is_default = 1 OR user_id = %s
    ''', (user_id,))
    kategori = cursor.fetchall()

    cursor.execute('''
        UPDATE challenges SET status = 'selesai'
        WHERE user_id = %s
        AND status = 'aktif'
        AND tanggal_selesai < CURDATE()
    ''', (user_id,))
    mysql.connection.commit()

    cursor.execute('''
        SELECT c.*, cat.nama as nama_kategori
        FROM challenges c
        LEFT JOIN categories cat ON c.category_id = cat.id
        WHERE c.user_id = %s AND c.status = 'aktif'
        ORDER BY c.created_at DESC
    ''', (user_id,))
    aktif_rows = cursor.fetchall()

    tantangan_aktif = []
    for t in aktif_rows:
        tgl_mulai = t['tanggal_mulai']
        tgl_selesai = t['tanggal_selesai']
        hari_berjalan = (date.today() - tgl_mulai).days + 1
        persen_progress = min(100, round((hari_berjalan / t['durasi']) * 100))

        cursor.execute('''
            SELECT COALESCE(SUM(jumlah), 0) as total
            FROM expenses
            WHERE user_id = %s
            AND category_id = %s
            AND tanggal BETWEEN %s AND CURDATE()
        ''', (user_id, t['category_id'], tgl_mulai))
        total_keluar = float(cursor.fetchone()['total'])
        total_budget = t['target_harian'] * hari_berjalan
        total_hemat = max(0, float(total_budget) - total_keluar)

        kalender = []
        for i in range(t['durasi']):
            tgl = tgl_mulai + timedelta(days=i)
            if tgl > date.today():
                status = 'belum'
            else:
                cursor.execute('''
                    SELECT COALESCE(SUM(jumlah), 0) as total
                    FROM expenses
                    WHERE user_id = %s
                    AND category_id = %s
                    AND tanggal = %s
                ''', (user_id, t['category_id'], tgl))
                keluar_hari = float(cursor.fetchone()['total'])
                status = 'berhasil' if keluar_hari <= float(t['target_harian']) else 'gagal'

            kalender.append({
                'tgl': tgl.strftime('%d'),
                'tanggal': str(tgl),
                'status': status
            })

        tantangan_aktif.append({
            **dict(t),
            'hari_berjalan': hari_berjalan,
            'persen_progress': persen_progress,
            'total_hemat': total_hemat,
            'kalender': kalender
        })

    cursor.execute('''
        SELECT c.*, cat.nama as nama_kategori
        FROM challenges c
        LEFT JOIN categories cat ON c.category_id = cat.id
        WHERE c.user_id = %s AND c.status != 'aktif'
        ORDER BY c.created_at DESC
    ''', (user_id,))
    selesai_rows = cursor.fetchall()

    tantangan_selesai = []
    for t in selesai_rows:
        cursor.execute('''
            SELECT COALESCE(SUM(jumlah), 0) as total
            FROM expenses
            WHERE user_id = %s
            AND category_id = %s
            AND tanggal BETWEEN %s AND %s
        ''', (user_id, t['category_id'], t['tanggal_mulai'], t['tanggal_selesai']))
        total_keluar = float(cursor.fetchone()['total'])
        total_budget = float(t['target_harian']) * t['durasi']
        total_hemat = max(0, total_budget - total_keluar)
        tantangan_selesai.append({**dict(t), 'total_hemat': total_hemat})

    success = request.args.get('success')
    pesan = 'Tantangan berhasil dimulai! Semangat!' if success else None

    return render_template('tantangan.html',
        kategori=kategori,
        tantangan_aktif=tantangan_aktif,
        tantangan_selesai=tantangan_selesai,
        success=pesan
    )


@app.route('/tantangan/buat', methods=['POST'])
def buat_tantangan():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user_id = session['user_id']
    from datetime import date, timedelta

    nama_tantangan = request.form['nama_tantangan']
    category_id = request.form['category_id']
    target_harian = request.form['target_harian']
    durasi = int(request.form['durasi'])

    tanggal_mulai = date.today()
    tanggal_selesai = tanggal_mulai + timedelta(days=durasi - 1)

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''
        INSERT INTO challenges
        (user_id, category_id, nama_tantangan, target_harian,
         durasi, tanggal_mulai, tanggal_selesai)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    ''', (user_id, category_id, nama_tantangan, target_harian,
          durasi, tanggal_mulai, tanggal_selesai))
    mysql.connection.commit()

    return redirect(url_for('tantangan') + '?success=1')

import random
import string

def generate_kode():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

@app.route('/family')
def family():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user_id = session['user_id']
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    cursor.execute('SELECT * FROM family_links WHERE mahasiswa_id = %s LIMIT 1',
                   (user_id,))
    link = cursor.fetchone()

    if not link:
        kode = generate_kode()
        cursor.execute('''
            INSERT INTO family_links (mahasiswa_id, kode_undangan, status)
            VALUES (%s, %s, 'pending')
        ''', (user_id, kode))
        mysql.connection.commit()
        kode_undangan = kode
    else:
        kode_undangan = link['kode_undangan']

    cursor.execute('''
        SELECT u.nama_lengkap, u.email
        FROM family_links fl
        JOIN users u ON fl.orangtua_id = u.id
        WHERE fl.mahasiswa_id = %s AND fl.status = 'aktif'
    ''', (user_id,))
    orangtua_terhubung = cursor.fetchall()

    success = request.args.get('success')
    error = request.args.get('error')

    return render_template('family.html',
        kode_undangan=kode_undangan,
        orangtua_terhubung=orangtua_terhubung,
        success='Akun berhasil terhubung!' if success else None,
        error='Kode undangan tidak valid!' if error else None
    )


@app.route('/family/hubungkan', methods=['POST'])
def hubungkan_family():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    orangtua_id = session['user_id']
    kode = request.form['kode_undangan'].upper().strip()
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Cari kode undangan
    cursor.execute('''
        SELECT * FROM family_links
        WHERE kode_undangan = %s AND status = 'pending'
    ''', (kode,))
    link = cursor.fetchone()

    if not link:
        return redirect(url_for('dashboard_orangtua') + '?error=1')

    # Hubungkan akun
    cursor.execute('''
        UPDATE family_links
        SET orangtua_id = %s, status = 'aktif'
        WHERE kode_undangan = %s
    ''', (orangtua_id, kode))
    mysql.connection.commit()

    return redirect(url_for('dashboard_orangtua') + '?success=1')


@app.route('/dashboard-orangtua')
def dashboard_orangtua():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    orangtua_id = session['user_id']
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    cursor.execute('''
        SELECT u.id, u.nama_lengkap, u.universitas
        FROM family_links fl
        JOIN users u ON fl.mahasiswa_id = u.id
        WHERE fl.orangtua_id = %s AND fl.status = 'aktif'
    ''', (orangtua_id,))
    anak_list = cursor.fetchall()

    data_anak = []
    for anak in anak_list:
        anak_id = anak['id']

        cursor.execute('''
            SELECT COALESCE(SUM(jumlah), 0) as total FROM income
            WHERE user_id = %s
            AND MONTH(tanggal) = MONTH(CURDATE())
            AND YEAR(tanggal) = YEAR(CURDATE())
        ''', (anak_id,))
        total_pemasukan = cursor.fetchone()['total']

        cursor.execute('''
            SELECT COALESCE(SUM(jumlah), 0) as total FROM expenses
            WHERE user_id = %s
            AND MONTH(tanggal) = MONTH(CURDATE())
            AND YEAR(tanggal) = YEAR(CURDATE())
        ''', (anak_id,))
        total_pengeluaran = cursor.fetchone()['total']

        saldo = total_pemasukan - total_pengeluaran
        fhs = min(100, max(0, round(
            ((saldo / total_pemasukan) * 100) if total_pemasukan > 0 else 0
        )))

        cursor.execute('''
            SELECT c.nama, SUM(e.jumlah) as total
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            WHERE e.user_id = %s
            AND MONTH(e.tanggal) = MONTH(CURDATE())
            AND YEAR(e.tanggal) = YEAR(CURDATE())
            GROUP BY c.nama
        ''', (anak_id,))
        pie_rows = cursor.fetchall()

        cursor.execute('''
            SELECT nama_tantangan, durasi, tanggal_mulai
            FROM challenges
            WHERE user_id = %s AND status = 'aktif'
        ''', (anak_id,))
        tantangan = cursor.fetchall()

        data_anak.append({
            'nama': anak['nama_lengkap'],
            'universitas': anak['universitas'] or '-',
            'total_pemasukan': total_pemasukan,
            'total_pengeluaran': total_pengeluaran,
            'saldo': saldo,
            'fhs': fhs,
            'pie_labels': [r['nama'] for r in pie_rows],
            'pie_data': [float(r['total']) for r in pie_rows],
            'tantangan': tantangan
        })

    success = request.args.get('success')
    error = request.args.get('error')

    return render_template('dashboard_orangtua.html',
        nama=session['nama'],
        data_anak=data_anak,
        sudah_hubungkan=len(data_anak) > 0,
        success='Berhasil terhubung dengan akun anak!' if success else None,
        error='Kode undangan tidak valid!' if error else None
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
