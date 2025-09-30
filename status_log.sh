#!/bin/sh
# Скрипт по сбору отчетной информации с компьютера. Версия 1.3
# Данный скрипт должен быть запущен через sudo
# Для обеспечения сбора информации об SSD нужен подключенный репозитарий из стандартного дистрибутива,
# т.к.в процессе работы скрипта может быть доустановлена утилита smartmontools если она не была установлена ранее 
# Запуск напрямую с подмонтированной флешки не допустим, запускать можно только с диска компьютера
# Автором данного скрипта является Подлесный Алексей
#
# Добавлено копирование hasp лицензий 
# Собираются настройки Integrity и сам проект (пока забирается вся дериктория /Integrity/Projects)
# 

file_dir="/var/tmp/archiv"
file_list="${file_dir}/${HOSTNAME}.txt"
file_hard="${file_dir}/${HOSTNAME}_hard.txt"
file_inst="${file_dir}/${HOSTNAME}_inst.txt"
file_ssd="${file_dir}/${HOSTNAME}_ssd.txt"
file_hasp="${file_dir}/${HOSTNAME}_hasp.txt"
current_date=$(date '+%Y-%m-%d-%H_%M')
name_log="${file_dir}/log_${HOSTNAME}_${current_date}.tar.gz"
archiv_log="log_archiv_${HOSTNAME}_${current_date}.tar.gz"
current_user=$(logname)
file_dir_secur="$(cd /share/IntegrityClientSecurity-* && pwd)/data/clientsecurity"

# Создаем временную директорию для складывания итогов
mkdir $file_dir
echo Версия ядра > $file_list
uname -r >> $file_list
echo >> $file_list

echo Вывод установленной версии >> $file_list
cat /etc/astra/build_version >> $file_list
echo >> $file_list

echo Вывод лицензии >> $file_list
cat /etc/astra_license >> $file_list
echo >> $file_list

echo Вывод состояния overlay >> $file_list
astra-overlay status >> $file_list
echo >> $file_list

echo Монитор безопасности astra-security-monitor >> $file_list
astra-security-monitor status >> $file_list
echo >> $file_list

echo Вывод размера партиций >> $file_list
df -h >> $file_list
echo >> $file_list

echo Вывод размера swap >> $file_list
free -l >> $file_list
echo >> $file_list

echo Вывод сетевых адресов >> $file_list
ip addr >> $file_list
echo >> $file_list

echo Вывод размера места на диске по каталогам >> $file_list
du -hs /var/* >> $file_list
du -hs /home/* >> $file_list 
du -hs /opt/* >> $file_list
du -hs /opt/repo/* >> $file_list

echo Вывод перечня установленного оборудования > $file_hard
lspci -vv >> $file_hard

echo Вывод списка установленных программ > $file_inst
dpkg-query -l >> $file_inst

# Проверяем наличие программы диогностики SSD и если ее нет, то устанавливаем из репозитария 
# Если репозитария нет, то будет ошибка на smartctl и скрипт продолжит работу дальше
echo Вывод состояния SSD > $file_ssd
if dpkg-query -s smartmontools | grep "ok installed" >> $file_list
then
echo Программа smartmontools уже установлена >> $file_ssd
else 
echo Устанавливаем smartmontools >> $file_ssd
apt install smartmontools 2>/dev/null
fi
echo >> $file_ssd
# Получаем список смонтированных устройств и запрашиваем параметры SMART
ssd_name=$(lsblk -ndo NAME)
for x in $ssd_name
do
smartctl -i -a /dev/$x >> $file_ssd
done
echo >> $file_list

# Пока проверяется только одиин параметр окончания действия пароля пользователя
echo Время жизни паролей пользователей системы >> $file_list
for user in $(cut -d: -f1 /etc/passwd) 
do 
  if id -u $user > /dev/null 2>&1; then 
    if [ $(id -u $user) -ge 1000 ]; then 
      expires=$(chage -l $user | grep "Срок действия пароля истекает" | awk -F: '{print $2}' | sed 's/,//g' | awk '{print $1,$2,$4}')
      if [ ! -z "$expires" ] && [ "$expires" != "никогда" ]; then 
        echo "$user Пароль истекает : $expires" >> $file_list
      fi 
    fi 
  fi 
done
echo >> $file_list

cp /etc/hosts $file_dir
cp /etc/apt/sources.list $file_dir
# Копируем файл настроек автоматического входа пользователя 
cp /etc/X11/fly-dm/fly-dmrc $file_dir

# Создание архива всех настроек графического киоска
tar -cPzf ${file_dir}/fly-kiosk.tar.gz -C /etc/fly-kiosk .
echo Архив fly-kiosk создан  >> $file_list

# Копируем в арохив настройки chrony 
if cp /etc/chrony/chrony.conf $file_dir 2>/dev/null
    then echo Копируем chrony.conf >> $file_list
    else echo Все пропало и chrony.conf отсутствует>> $file_list
fi 
# Проверяем залочку TTY консолей
if cp /etc/X11/xorg.conf $file_dir 2>/dev/null
    then echo Копируем xorg.conf >> $file_list
    else echo Все пропало и xorg.conf отсутствует>> $file_list
fi
# Созраняем перечень лицензий с ключа Integrity
if curl -o $file_hasp http://127.0.0.1:1947/csv/features.txt 2>/dev/null
    then echo Список лицензий скопирован >> $file_list
    else echo Все пропало и лицензий Integrity не обнаружено>> $file_list
fi 
# Созраняем перечень лицензий с ключа Integrity Guardant
if license_wizard --console --list >> $file_hasp 
    then echo Список лицензий Guardant скопирован >> $file_list
    else echo Все пропало и лицензий Integrity на ключе Guardsnt не обнаружено>> $file_list
fi 
# Копируем в архив файл IntegrityClientSecurity
if cp $file_dir_secur  $file_dir 2>/dev/null
    then echo Копируем clientsecurity >> $file_list
    else echo Все пропало и файл clientsecurity отсутствует>> $file_list
fi
# Копируем в архив директорию /etc/HMI
cp -r /etc/HMI  $file_dir 2>/dev/null
# Копируем в архив директорию /etc/Integrity
cp -r /etc/Integrity  $file_dir 2>/dev/null
# Копируем в архив  /usr/bin/IntegrityDataTransport.xml
if cp /usr/bin/IntegrityDataTransport.xml  $file_dir 2>/dev/null
    then echo Копируем /usr/bin/IntegrityDataTransport.xml >> $file_list
    else echo Все пропало и файла /usr/bin/IntegrityDataTransport.xml нет>> $file_list
fi
# Копируем в архив директорию /var/IntegrityEnvCtrl
cp -r /var/IntegrityEnvCtrl $file_dir 2>/dev/null

# Копируем в архив директорию c проектом
cp -r /Integrity/Projects $file_dir 2>/dev/null

# Создание архива всех логов
tar -cPzf $name_log -C /var/log .
echo Архив логов создан  >> $file_list

# Все пакуем и кладем в home 
tar -cPzf $archiv_log -C $file_dir .

# Удаляем за собой временную директорию
rm -rf $file_dir
# Меняем хозяина архива с root на админа
chown ${current_user}: $archiv_log
 